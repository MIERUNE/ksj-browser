"""原本取得・再利用をローカルHTTPと実QGISで検証する。"""

import io
import zipfile
from pathlib import Path

import pytest
from qgis.core import QgsApplication, QgsSettings, QgsTask
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication

from ksj import local_storage
from tests.helpers import mock_download, pump_until, zip_bytes


@pytest.fixture
def storage_settings(qgis_app, tmp_path, monkeypatch):
    key = "ksj-tests/download-directory"
    monkeypatch.setattr(local_storage, "DIRECTORY_KEY", key)
    monkeypatch.setattr(local_storage, "MODE_KEY", key + "-mode")
    QgsSettings().remove(key)
    QgsSettings().remove(local_storage.MODE_KEY)
    yield tmp_path / "保存データ"
    QgsSettings().remove(key)
    QgsSettings().remove(local_storage.MODE_KEY)


def run_workers(app, functions):
    results, errors, done = {}, [], set()

    def finish(index, error, result=None):
        done.add(index)
        results[index] = result
        if error is not None:
            errors.append(error)

    tasks = []
    for index, function in enumerate(functions):
        task = QgsTask.fromFunction(
            "保存テスト",
            lambda task, function=function: function(),
            on_finished=lambda error, result=None, index=index: finish(
                index, error, result
            ),
        )
        tasks.append(task)
        QgsApplication.taskManager().addTask(task)
    # QGISのネットワーク初期化・標準タイムアウトを含めて待つ。
    pump_until(app, lambda: len(done) == len(tasks), timeout=90, interval=0.005)
    if errors:
        raise errors[0]
    return [results[index] for index in range(len(tasks))]


def test_choose_directory_remembers_and_cancel_keeps_previous(
    storage_settings, monkeypatch
):
    assert local_storage.download_directory() == ""
    monkeypatch.setattr(
        local_storage.QFileDialog,
        "getExistingDirectory",
        lambda *args: str(storage_settings),
    )
    assert local_storage.choose_download_directory() == str(storage_settings)
    assert storage_settings.is_dir()
    assert local_storage.download_directory() == str(storage_settings)
    monkeypatch.setattr(
        local_storage.QFileDialog, "getExistingDirectory", lambda *args: ""
    )
    assert local_storage.choose_download_directory() == ""
    assert local_storage.download_directory() == str(storage_settings)


def test_download_reuses_completed_file_without_requests(qgis_app, tmp_path, http_data):
    def download():
        return local_storage.ensure_local_data(http_data["url"], str(tmp_path))

    first = run_workers(qgis_app, [download])[0]
    assert (Path(first) / "point.geojson").is_file()
    assert not list(tmp_path.rglob("*.zip"))
    http_data["status"] = 503
    assert run_workers(qgis_app, [download])[0] == first
    assert http_data["requests"] == ["/data.zip"]
    assert "/vsicurl/" not in first


def test_same_url_concurrent_download_only_fetches_once(qgis_app, tmp_path, http_data):
    http_data["delay"] = 0.1
    paths = run_workers(
        qgis_app,
        [
            lambda: local_storage.ensure_local_data(http_data["url"], str(tmp_path))
            for _ in range(2)
        ],
    )
    assert paths[0] == paths[1]
    assert http_data["requests"] == ["/data.zip"]


def test_different_urls_with_same_filename_do_not_collide(
    qgis_app, tmp_path, http_data
):
    paths = run_workers(
        qgis_app,
        [
            lambda query=query: local_storage.ensure_local_data(
                http_data["url"] + query, str(tmp_path)
            )
            for query in ("?year=2024", "?year=2025")
        ],
    )
    assert paths[0] != paths[1]
    assert all((Path(path) / "point.geojson").is_file() for path in paths)


@pytest.mark.parametrize("failure", ["http", "zip", "html", "empty", "truncated"])
def test_failure_leaves_no_completed_file_and_can_retry(
    qgis_app, tmp_path, http_data, failure
):
    original = http_data["body"]
    if failure == "http":
        http_data["status"] = 404
    elif failure == "truncated":
        http_data["length"] = len(original) + 100
    else:
        http_data["body"] = {
            "zip": b"broken zip",
            "html": b"<!doctype html><html>captcha</html>",
            "empty": b"",
        }[failure]

    def download():
        return local_storage.ensure_local_data(http_data["url"], str(tmp_path))

    with pytest.raises(local_storage.DownloadError):
        run_workers(qgis_app, [download])
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.part"))
    http_data.update(body=original, status=200, length=len(original))
    assert (Path(run_workers(qgis_app, [download])[0]) / "point.geojson").is_file()


def test_cancel_download_leaves_no_completed_file(qgis_app, tmp_path, http_data):
    http_data["delay"] = 0.5

    def download():
        return local_storage.ensure_local_data(
            http_data["url"],
            str(tmp_path),
            is_canceled=lambda: bool(http_data["requests"]),
        )

    with pytest.raises(local_storage.DownloadCanceled):
        run_workers(qgis_app, [download])
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.part"))


def test_browser_unconfigured_lists_files_without_downloading(
    storage_settings, monkeypatch
):
    from ksj.catalog_browser import KsjResourceItem
    from ksj import remote_zip

    def unexpected(*args, **kwargs):
        pytest.fail("一覧表示でデータ本体を取得してはいけない")

    monkeypatch.setattr(local_storage, "ensure_local_data", unexpected)
    monkeypatch.setattr(remote_zip, "list_members", lambda *args: ["point.geojson"])
    item = KsjResourceItem(
        None,
        "/test/data",
        {"filename": "data.zip", "url": "https://example.org/data.zip"},
    )
    choices = item.createChildren()
    assert len(choices) == 1
    assert choices[0].name() == "point.geojson"
    monkeypatch.setattr(local_storage, "configure_loading", lambda *args: False)
    assert choices[0].handleDoubleClick()
    assert local_storage.download_directory() == ""


def test_root_menu_can_change_directory(storage_settings, monkeypatch):
    from ksj.browser import KsjRootItem

    root = KsjRootItem()
    actions = root.actions(None)
    action = next(a for a in actions if "保存先" in a.text() and "設定" in a.text())

    def accept():
        dialog = QApplication.activeModalWidget()
        dialog.directory.setText(str(storage_settings))
        dialog.accept()

    QTimer.singleShot(0, accept)
    action.trigger()
    assert local_storage.download_directory() == str(storage_settings)


@pytest.mark.parametrize("zipped", [True, False])
def test_browser_download_and_project_reopen_never_reconnect(
    qgis_app, qgis_new_project, storage_settings, tmp_path, http_data, zipped
):
    from qgis.core import QgsProject
    from ksj.catalog_browser import KsjResourceItem
    from ksj import layer_loading

    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    http_data["range_support"] = True
    if not zipped:
        with zipfile.ZipFile(io.BytesIO(http_data["body"])) as archive:
            http_data["body"] = archive.read("point.geojson")
        http_data["url"] = http_data["url"].replace("data.zip", "point.geojson")
    item = KsjResourceItem(
        None,
        "/test/data",
        {
            "filename": "data.zip" if zipped else "point.geojson",
            "url": http_data["url"],
        },
    )
    children = run_workers(qgis_app, [item.createChildren])[0]
    assert not list(storage_settings.iterdir())
    assert children[0].handleDoubleClick()
    pump_until(qgis_app, lambda: not layer_loading.pending, timeout=10)
    project = QgsProject.instance()
    uri = list(project.mapLayers().values())[0].source()
    assert "/vsi" not in uri and str(storage_settings) in uri
    assert Path(uri).is_file()
    path = tmp_path / "test.qgz"
    assert project.write(str(path))
    before = len(http_data["requests"])
    http_data["status"] = 503
    project.clear()
    assert project.read(str(path))
    layers = list(project.mapLayers().values())
    assert len(layers) == 1 and layers[0].isValid()
    assert layers[0].featureCount() == 1
    assert next(layers[0].getFeatures())["name"] == "test"
    run_workers(qgis_app, [item.createChildren])
    assert len(http_data["requests"]) == before
    assert before >= 1


def test_mesh_downloads_once_and_uses_local_sources(
    qgis_app, qgis_new_project, storage_settings, http_data, monkeypatch
):
    from qgis import utils
    from qgis.core import QgsProject
    from ksj import mesh_index

    monkeypatch.setattr(utils, "iface", None)
    choices = []

    def select(*args):
        choices.append(True)
        return str(storage_settings)

    monkeypatch.setattr(local_storage.QFileDialog, "getExistingDirectory", select)
    index = mesh_index.add_mesh_index(
        "試験", [{"filename": "data.zip", "url": http_data["url"], "region": "5339"}]
    )
    feature = next(index.getFeatures())
    project = QgsProject.instance()
    for _ in range(2):
        mesh_index.load_mesh(index.id(), feature.id())
        pump_until(qgis_app, lambda: not mesh_index._pending, timeout=10)
        loaded = [
            layer for layer in project.mapLayers().values() if layer.id() != index.id()
        ]
        assert len(loaded) == 1 and loaded[0].featureCount() == 1
        assert "/vsi" not in loaded[0].source()
        assert Path(loaded[0].source().split("|", 1)[0]).is_file()
        project.removeMapLayer(loaded[0].id())
    assert choices == [True]
    assert http_data["requests"] == ["/data.zip"]


def test_corrupt_compressed_zip_is_reported_and_removed(tmp_path, monkeypatch):
    damaged = bytearray(
        zip_bytes([("data.txt", "data" * 100)], compression=zipfile.ZIP_DEFLATED)
    )
    damaged[30 + len("data.txt")] = 7  # DEFLATEの予約ブロック種別に変えて破損させる。
    mock_download(monkeypatch, bytes(damaged))
    with pytest.raises(local_storage.DownloadError, match="ZIP"):
        local_storage.ensure_local_data("https://example.org/data.zip", str(tmp_path))
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.part"))


def test_valid_zip_with_html_documentation_is_accepted(tmp_path, monkeypatch):
    mock_download(
        monkeypatch,
        zip_bytes(
            [
                ("README.html", "<!doctype html><html>説明</html>"),
                ("table.csv", "name,value\ntest,1\n"),
            ],
            compression=zipfile.ZIP_STORED,
        ),
    )
    path = local_storage.ensure_local_data(
        "https://example.org/data.zip", str(tmp_path)
    )
    assert (Path(path) / "table.csv").read_bytes() == b"name,value\ntest,1\n"
    assert not list(tmp_path.rglob("*.zip"))


def test_bad_directory_does_not_change_setting(storage_settings, monkeypatch):
    storage_settings.write_text("file")
    monkeypatch.setattr(
        local_storage.QFileDialog,
        "getExistingDirectory",
        lambda *args: str(storage_settings),
    )
    warnings = []
    monkeypatch.setattr(
        local_storage.QMessageBox, "warning", lambda *args: warnings.append(args)
    )
    assert local_storage.choose_download_directory() == ""
    assert local_storage.download_directory() == ""
    assert len(warnings) == 1


def test_cancel_before_request_and_unwritable_destination_do_not_download(
    tmp_path, monkeypatch
):
    def unexpected(*args):
        pytest.fail("取得を開始してはいけません")

    monkeypatch.setattr(local_storage, "_download", unexpected)
    with pytest.raises(local_storage.DownloadCanceled):
        local_storage.ensure_local_data(
            "https://example.org/a.zip", str(tmp_path), lambda: True
        )
    file = tmp_path / "file"
    file.write_text("not a directory")
    with pytest.raises(local_storage.DownloadError, match="保存"):
        local_storage.ensure_local_data("https://example.org/a.zip", str(file))


@pytest.mark.parametrize("nested", [False, True])
def test_project_can_move_with_extracted_files(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, nested
):
    from qgis.core import QgsProject, QgsVectorLayer

    original = tmp_path / "original"
    original.mkdir()
    data = zip_bytes([("table.csv", "name,value\ntest,1\n")])
    if nested:
        data = zip_bytes([("inner.zip", data)])
    mock_download(monkeypatch, data)
    root = Path(
        local_storage.ensure_local_data("https://example.org/data.zip", str(original))
    )
    table = next(root.rglob("table.csv"))
    layer = QgsVectorLayer(str(table), "table", "ogr")
    assert layer.isValid()
    assert "/vsi" not in layer.source()
    project = QgsProject.instance()
    project.addMapLayer(layer)
    assert project.write(str(original / "test.qgz"))
    project.clear()
    layer = None
    moved = tmp_path / "shared"
    original.rename(moved)
    assert project.read(str(moved / "test.qgz"))
    restored = list(project.mapLayers().values())[0]
    assert restored.isValid() and restored.featureCount() == 1
    assert next(restored.getFeatures())["name"] == "test"


def test_browser_model_uses_latest_settings_without_repopulating(
    qgis_app, qgis_new_project, storage_settings, tmp_path, monkeypatch
):
    from qgis.core import QgsBrowserModel, QgsProject
    from ksj import layer_loading
    from ksj.browser import KsjDataItemProvider, KsjRootItem
    from ksj.catalog_browser import KsjResourceItem

    calls = mock_download(monkeypatch, b"name,value\nsample,1\n")

    class Root(KsjRootItem):
        def createChildren(self):
            return [
                KsjResourceItem(
                    self,
                    "/ksj/test",
                    {"filename": "table.csv", "url": "https://example.org/table.csv"},
                )
            ]

    class Provider(KsjDataItemProvider):
        def createDataItem(self, path, parent):
            return Root() if path == "" else None

    def wait_for(predicate):
        pump_until(qgis_app, predicate, timeout=5)

    registry = QgsApplication.dataItemProviderRegistry()
    provider = Provider()
    registry.addProvider(provider)
    model = QgsBrowserModel()
    try:
        model.initialize()
        root = model.findPath("/ksj")
        model.fetchMore(root)
        wait_for(lambda: model.rowCount(root) > 0)
        resource = model.index(0, 0, root)
        model.fetchMore(resource)
        wait_for(lambda: model.rowCount(resource) > 0)
        item = model.dataItem(model.index(0, 0, resource))
        assert item.name() == "table.csv" and calls == []

        def configure(directory):
            dialog = QApplication.activeModalWidget()
            dialog.directory.setText(str(directory))
            dialog.accept()

        QTimer.singleShot(0, lambda: configure(storage_settings))
        assert item.handleDoubleClick()
        wait_for(lambda: not layer_loading.pending)
        assert calls == ["https://example.org/table.csv"]
        existing = list(QgsProject.instance().mapLayers().values())[0]
        old_source = existing.source()
        changed = tmp_path / "新しい保存先"
        action = next(
            a
            for a in model.dataItem(resource).actions(None)
            if "保存先" in a.text() and "設定" in a.text()
        )
        QTimer.singleShot(0, lambda: configure(changed))
        action.trigger()
        assert len(calls) == 1
        assert model.dataItem(model.index(0, 0, resource)) is item
        assert item.handleDoubleClick()
        wait_for(lambda: not layer_loading.pending)
        assert len(calls) == 2
        assert any(
            str(changed) in layer.source()
            for layer in QgsProject.instance().mapLayers().values()
        )
        assert existing.source() == old_source and existing.featureCount() == 1
    finally:
        layer_loading.cancel_pending()
        model.removeRootItems()
        registry.removeProvider(provider)
        qgis_app.processEvents()
