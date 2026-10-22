"""ブラウザ内の待機表示を実際のレイヤー追加タスクで検証する。"""

import json
import threading

import pytest
from qgis.core import QgsDataItem, QgsProject, QgsSettings
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QCoreApplication, QEvent
from qgis.PyQt.QtWidgets import QMenu

from ksj import catalog_browser, layer_loading, local_storage, remote_zip
from tests.helpers import point_file, pump_until, run_workers, wait_for_layer_loading


@pytest.fixture
def loading(qgis_app, qgis_new_project, storage_settings, tmp_path, monkeypatch):
    """取得だけを保留し、GUIの更新とタスクの完了処理は本物を使う。"""
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    source = point_file(tmp_path)
    release = threading.Event()
    failure = []

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

    yield item, release, failure
    release.set()
    wait_for_layer_loading(qgis_app)


@pytest.mark.parametrize("operation", ["double_click", "menu", "drop"])
@pytest.mark.parametrize("mode", ["save", "temporary"])
def test_loading_indicator_covers_add_operations_and_restores_item(
    qgis_app, loading, storage_settings, operation, mode
):
    create, release, _ = loading
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    QgsSettings().setValue(local_storage.MODE_KEY, mode)
    item, other = create(), create("other.geojson")
    original_icon = item.icon().pixmap(24, 24).toImage()
    original_tooltip = item.toolTip()
    original_sort = item.sortKey()
    if operation == "double_click":
        item.handleDoubleClick()
    elif operation == "menu":
        menu = QMenu()
        item.actions(menu)[0].trigger()
    else:
        layer_loading.KsjDropHandler().handleCustomUriDrop(item.mimeUris()[0])

    assert "読み込み中" in item.name()
    pump_until(
        qgis_app,
        lambda: item.icon().pixmap(24, 24).toImage() != original_icon,
        timeout=2,
    )
    first_frame = item.icon().pixmap(24, 24).toImage()
    assert not first_frame.isNull()
    pump_until(
        qgis_app,
        lambda: item.icon().pixmap(24, 24).toImage() != first_frame,
        timeout=2,
    )
    assert "読み込み中" in item.toolTip()
    assert item.sortKey() == original_sort
    assert not item.hasChildren()
    assert other.name() == "other.geojson"
    uri = item.mimeUris()[0]
    assert uri.name == "dams.geojson"
    assert json.loads(uri.uri)["name"] == "dams.geojson"
    # 連打しても表示名がレイヤー名へ混ざらず、二重追加もしない。
    item.handleDoubleClick()
    release.set()
    wait_for_layer_loading(qgis_app)
    assert item.name() == "dams.geojson"
    assert item.state() == QgsDataItem.Populated
    assert item.toolTip() == original_tooltip
    assert item.icon().pixmap(24, 24).toImage() == original_icon
    assert [layer.name() for layer in QgsProject.instance().mapLayers().values()] == [
        "dams.geojson"
    ]


def test_failed_loading_restores_item_and_allows_retry(qgis_app, loading, monkeypatch):
    create, release, failure = loading
    messages = []
    monkeypatch.setattr(layer_loading, "notify", lambda text, **kw: messages.append(text))
    item = create()
    failure.append("取得失敗")
    item.handleDoubleClick()
    assert "読み込み中" in item.name()
    release.set()
    wait_for_layer_loading(qgis_app)
    assert item.name() == "dams.geojson"
    assert item.state() == QgsDataItem.Populated
    assert not QgsProject.instance().mapLayers()
    assert "取得失敗" in messages[0]
    failure.clear()
    item.handleDoubleClick()
    assert "読み込み中" in item.name()
    wait_for_layer_loading(qgis_app)
    assert len(QgsProject.instance().mapLayers()) == 1
    assert item.name() == "dams.geojson"


@pytest.mark.parametrize("cancel_all", [False, True])
def test_cancel_restores_loading_item(qgis_app, loading, cancel_all):
    create, _, _ = loading
    item = create()
    item.handleDoubleClick()
    assert "読み込み中" in item.name()
    task = next(iter(layer_loading.pending.values()))
    done = []
    task.taskTerminated.connect(lambda: done.append(True))
    if cancel_all:
        layer_loading.cancel_pending()
    else:
        task.cancel()
    pump_until(qgis_app, lambda: bool(done), timeout=5)
    assert item.name() == "dams.geojson"
    assert item.state() == QgsDataItem.Populated
    assert not QgsProject.instance().mapLayers()


def test_recreated_item_tracks_running_task_without_retaining_deleted_item(
    qgis_app, loading
):
    create, release, _ = loading
    original = create()
    original.handleDoubleClick()
    original.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(original)

    def recreate():
        item = create()
        # GUIへ移す前にワーカーのイベントループが回っても描画を始めない。
        QCoreApplication.processEvents()
        assert item.loading_icon is None
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
    qgis_app, loading, storage_settings, replace
):
    create, release, _ = loading
    item = create()
    item.handleDoubleClick()
    old = next(iter(layer_loading.pending.values()))
    terminated = []
    old.taskTerminated.connect(lambda: terminated.append(True))
    if replace:
        layer_loading.cancel_pending()
    else:
        # 同じファイルを別の追加方法で読み込む場合も、残るタスクを表示する。
        storage_settings.mkdir()
        QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
        QgsSettings().setValue(local_storage.MODE_KEY, "save")
        old.cancel()
    item.handleDoubleClick()
    pump_until(qgis_app, lambda: bool(terminated), timeout=5)
    assert "読み込み中" in item.name()
    assert len(layer_loading.pending) == 1
    release.set()
    wait_for_layer_loading(qgis_app)
    assert item.name() == "dams.geojson"
    assert len(QgsProject.instance().mapLayers()) == 1


def test_canceling_settings_does_not_show_loading(qgis_app, loading, monkeypatch):
    create, _, _ = loading
    QgsSettings().setValue(local_storage.MODE_KEY, "save")
    monkeypatch.setattr(local_storage, "configure_loading", lambda: False)
    item = create()
    item.handleDoubleClick()
    assert not layer_loading.pending
    assert item.name() == "dams.geojson"
    assert item.state() == QgsDataItem.Populated
