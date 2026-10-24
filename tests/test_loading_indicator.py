"""ブラウザ内の待機表示を実際のレイヤー追加タスクで検証する。"""

import json
import threading

import pytest
from qgis.core import QgsDataItem, QgsProject, QgsSettings
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QCoreApplication, QEvent
from qgis.PyQt.QtWidgets import QMenu

from ksj import catalog_browser, layer_loading, local_storage, remote_zip
from tests.helpers import (
    icon_image,
    point_file,
    pump_until,
    run_workers,
    termination_of,
    wait_for_layer_loading,
)


@pytest.fixture
def release():
    """set() するまで取得を保留する。"""
    return threading.Event()


@pytest.fixture
def failure():
    """メッセージを入れると取得をその理由で失敗させる。"""
    return []


@pytest.fixture
def make_item(
    qgis_app,
    qgis_new_project,
    storage_settings,
    tmp_path,
    monkeypatch,
    release,
    failure,
):
    """取得だけを保留し、GUIの更新とタスクの完了処理は本物を使う。"""
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    source = point_file(tmp_path)

    def fetch(url, member, directory, is_canceled, progress):
        while not release.wait(0.01):
            local_storage._check_canceled(is_canceled)
        if failure:
            raise local_storage.DownloadError(failure[0])
        return str(source)

    monkeypatch.setattr(remote_zip, "ensure_member", fetch)

    def item(member="dams.geojson"):
        return catalog_browser.KsjFileItem(
            None, member, "/test/" + member, "https://example.org/data.zip", member
        )

    yield item
    release.set()
    wait_for_layer_loading(qgis_app)


@pytest.mark.parametrize("operation", ["double_click", "menu", "drop"])
def test_loading_indicator_covers_add_operations_and_restores_item(
    qgis_app, make_item, release, operation
):
    item = make_item()
    original_icon = icon_image(item)
    original_tooltip = item.toolTip()
    if operation == "double_click":
        item.handleDoubleClick()
    elif operation == "menu":
        menu = QMenu()
        item.actions(menu)[0].trigger()
    else:
        layer_loading.KsjDropHandler().handleCustomUriDrop(item.mimeUris()[0])

    assert "読み込み中" in item.name()
    assert "読み込み中" in item.toolTip()
    pump_until(qgis_app, lambda: icon_image(item) != original_icon, timeout=2)
    first_frame = icon_image(item)
    assert not first_frame.isNull()
    pump_until(qgis_app, lambda: icon_image(item) != first_frame, timeout=2)
    # 連打しても表示名がレイヤー名へ混ざらず、二重追加もしない。
    item.handleDoubleClick()
    release.set()
    wait_for_layer_loading(qgis_app)
    assert item.name() == "dams.geojson"
    assert item.state() == QgsDataItem.State.Populated
    assert item.toolTip() == original_tooltip
    assert icon_image(item) == original_icon
    assert [layer.name() for layer in QgsProject.instance().mapLayers().values()] == [
        "dams.geojson"
    ]


def test_loading_item_keeps_filename_for_sort_drag_and_other_items(qgis_app, make_item):
    item, other = make_item(), make_item("other.geojson")
    original_sort = item.sortKey()
    item.handleDoubleClick()
    assert "読み込み中" in item.name()
    assert item.sortKey() == original_sort
    assert not item.hasChildren()
    assert other.name() == "other.geojson"
    uri = item.mimeUris()[0]
    assert uri.name == "dams.geojson"
    assert json.loads(uri.uri)["name"] == "dams.geojson"


def test_failed_loading_restores_item_and_allows_retry(
    qgis_app, make_item, release, failure, monkeypatch
):
    messages = []
    monkeypatch.setattr(
        layer_loading, "notify", lambda text, **kw: messages.append(text)
    )
    item = make_item()
    failure.append("取得失敗")
    item.handleDoubleClick()
    assert "読み込み中" in item.name()
    release.set()
    wait_for_layer_loading(qgis_app)
    assert item.name() == "dams.geojson"
    assert item.state() == QgsDataItem.State.Populated
    assert not QgsProject.instance().mapLayers()
    assert "取得失敗" in messages[0]
    failure.clear()
    item.handleDoubleClick()
    assert "読み込み中" in item.name()
    wait_for_layer_loading(qgis_app)
    assert len(QgsProject.instance().mapLayers()) == 1
    assert item.name() == "dams.geojson"


@pytest.mark.parametrize("cancel_all", [False, True])
def test_cancel_restores_loading_item(qgis_app, make_item, cancel_all):
    item = make_item()
    item.handleDoubleClick()
    assert "読み込み中" in item.name()
    task = next(iter(layer_loading.pending.values()))
    ended = termination_of(task)
    if cancel_all:
        layer_loading.cancel_pending()
    else:
        task.cancel()
    pump_until(qgis_app, ended, timeout=5)
    assert item.name() == "dams.geojson"
    assert item.state() == QgsDataItem.State.Populated
    assert not QgsProject.instance().mapLayers()


def test_recreated_item_tracks_running_task_without_retaining_deleted_item(
    qgis_app, make_item, release
):
    original = make_item()
    original.handleDoubleClick()
    original.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(original)

    def recreate():
        item = make_item()
        # GUIへ移す前にワーカーのイベントループが回っても描画を始めない。
        QCoreApplication.processEvents()
        assert "読み込み中" not in item.name()
        item.moveToThread(qgis_app.thread())
        return item

    recreated = run_workers(qgis_app, [recreate])[0]
    pump_until(qgis_app, lambda: "読み込み中" in recreated.name(), timeout=2)
    release.set()
    wait_for_layer_loading(qgis_app)
    assert recreated.name() == "dams.geojson"
    assert len(QgsProject.instance().mapLayers()) == 1


@pytest.mark.parametrize("replace", [False, True])
def test_old_task_completion_does_not_clear_another_load(
    qgis_app, make_item, release, storage_settings, replace
):
    item = make_item()
    item.handleDoubleClick()
    old = next(iter(layer_loading.pending.values()))
    ended = termination_of(old)
    if replace:
        layer_loading.cancel_pending()
    else:
        # 同じファイルを別の追加方法で読み込む場合も、残るタスクを表示する。
        storage_settings.mkdir()
        QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
        QgsSettings().setValue(local_storage.MODE_KEY, "save")
        old.cancel()
    item.handleDoubleClick()
    pump_until(qgis_app, ended, timeout=5)
    assert "読み込み中" in item.name()
    assert len(layer_loading.pending) == 1
    release.set()
    wait_for_layer_loading(qgis_app)
    assert item.name() == "dams.geojson"
    assert len(QgsProject.instance().mapLayers()) == 1


def test_canceling_settings_does_not_show_loading(qgis_app, make_item, monkeypatch):
    QgsSettings().setValue(local_storage.MODE_KEY, "save")
    monkeypatch.setattr(local_storage, "configure_loading", lambda: False)
    item = make_item()
    item.handleDoubleClick()
    assert not layer_loading.pending
    assert item.name() == "dams.geojson"
    assert item.state() == QgsDataItem.State.Populated
