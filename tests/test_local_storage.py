"""原本取得・再利用をローカルHTTPと実QGISで検証する。"""

import io
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from qgis.core import QgsApplication, QgsSettings, QgsTask

from ksj import local_storage


@pytest.fixture
def storage_settings(qgis_app, tmp_path, monkeypatch):
    key = "ksj-tests/download-directory"
    monkeypatch.setattr(local_storage, "DIRECTORY_KEY", key)
    QgsSettings().remove(key)
    yield tmp_path / "保存データ"
    QgsSettings().remove(key)


@pytest.fixture
def http_data():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "point.geojson",
            '{"type":"FeatureCollection","features":[{"type":"Feature",'
            '"properties":{"name":"test"},"geometry":'
            '{"type":"Point","coordinates":[140,40]}}]}',
        )
    state = {"body": buffer.getvalue(), "requests": [], "status": 200, "delay": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append(self.path)
            self.send_response(state["status"])
            body = state["body"]
            self.send_header("Content-Length", str(state.get("length", len(body))))
            self.end_headers()
            time.sleep(state["delay"])
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{server.server_port}/data.zip"
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


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
    deadline = time.monotonic() + 90
    while len(done) < len(tasks) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert len(done) == len(tasks), "取得が時間内に完了しませんでした"
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
        return local_storage.ensure_local_file(http_data["url"], str(tmp_path))

    first = run_workers(qgis_app, [download])[0]
    assert Path(first).read_bytes() == http_data["body"]
    http_data["status"] = 503
    assert run_workers(qgis_app, [download])[0] == first
    assert http_data["requests"] == ["/data.zip"]
    assert "/vsicurl/" not in first


def test_same_url_concurrent_download_only_fetches_once(qgis_app, tmp_path, http_data):
    http_data["delay"] = 0.1
    paths = run_workers(
        qgis_app,
        [
            lambda: local_storage.ensure_local_file(http_data["url"], str(tmp_path))
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
            lambda query=query: local_storage.ensure_local_file(
                http_data["url"] + query, str(tmp_path)
            )
            for query in ("?year=2024", "?year=2025")
        ],
    )
    assert paths[0] != paths[1]
    assert all(Path(path).suffix == ".zip" for path in paths)


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
        return local_storage.ensure_local_file(http_data["url"], str(tmp_path))

    with pytest.raises(local_storage.DownloadError):
        run_workers(qgis_app, [download])
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.part"))
    http_data.update(body=original, status=200, length=len(original))
    assert Path(run_workers(qgis_app, [download])[0]).is_file()


def test_cancel_download_leaves_no_completed_file(qgis_app, tmp_path, http_data):
    http_data["delay"] = 0.5

    def download():
        return local_storage.ensure_local_file(
            http_data["url"],
            str(tmp_path),
            is_canceled=lambda: bool(http_data["requests"]),
        )

    with pytest.raises(local_storage.DownloadCanceled):
        run_workers(qgis_app, [download])
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.part"))


def test_browser_unconfigured_offers_folder_choice_without_download(
    storage_settings, monkeypatch
):
    from ksj.catalog_browser import KsjResourceItem

    def unexpected(*args, **kwargs):
        pytest.fail("保存先未設定では通信しない")

    monkeypatch.setattr(local_storage, "ensure_local_file", unexpected)
    item = KsjResourceItem(
        None,
        "/test/data",
        {"filename": "data.zip", "url": "https://example.org/data.zip"},
    )
    choices = item.createChildren()
    assert len(choices) == 1
    assert "保存先" in choices[0].name()
    monkeypatch.setattr(
        local_storage.QFileDialog, "getExistingDirectory", lambda *args: ""
    )
    assert choices[0].handleDoubleClick()
    assert local_storage.download_directory() == ""


def test_root_menu_can_change_directory(storage_settings, monkeypatch):
    from ksj.browser import KsjRootItem

    root = KsjRootItem()
    actions = root.actions(None)
    action = next(a for a in actions if "保存先" in a.text() and "変更" in a.text())
    monkeypatch.setattr(
        local_storage.QFileDialog,
        "getExistingDirectory",
        lambda *args: str(storage_settings),
    )
    action.trigger()
    assert local_storage.download_directory() == str(storage_settings)


@pytest.mark.parametrize("zipped", [True, False])
def test_browser_download_and_project_reopen_never_reconnect(
    qgis_app, qgis_new_project, storage_settings, tmp_path, http_data, zipped
):
    from qgis.core import QgsProject
    from ksj.catalog_browser import KsjResourceItem

    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
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
    uri = children[0].mimeUris()[0].uri
    assert "/vsicurl/" not in uri and str(storage_settings) in uri
    assert children[0].handleDoubleClick()
    project = QgsProject.instance()
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
    assert len(http_data["requests"]) == before == 1


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
        deadline = time.monotonic() + 10
        while mesh_index._pending and time.monotonic() < deadline:
            qgis_app.processEvents()
            time.sleep(0.005)
        assert not mesh_index._pending
        loaded = [
            layer for layer in project.mapLayers().values() if layer.id() != index.id()
        ]
        assert len(loaded) == 1 and loaded[0].featureCount() == 1
        assert "/vsicurl/" not in loaded[0].source()
        project.removeMapLayer(loaded[0].id())
    assert choices == [True]
    assert http_data["requests"] == ["/data.zip"]


def test_corrupt_compressed_zip_is_reported_and_removed(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.txt", "data" * 100)
    damaged = bytearray(buffer.getvalue())
    damaged[30 + len("data.txt")] = 7  # DEFLATEの予約ブロック種別に変えて破損させる。
    monkeypatch.setattr(
        local_storage, "_download", lambda url, path, *args: path.write_bytes(damaged)
    )
    with pytest.raises(local_storage.DownloadError, match="ZIP"):
        local_storage.ensure_local_file("https://example.org/data.zip", str(tmp_path))
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.part"))


def test_valid_zip_with_html_documentation_is_accepted(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("README.html", "<!doctype html><html>説明</html>")
        archive.writestr("table.csv", "name,value\ntest,1\n")
    monkeypatch.setattr(
        local_storage,
        "_download",
        lambda url, path, *args: path.write_bytes(buffer.getvalue()),
    )
    path = local_storage.ensure_local_file(
        "https://example.org/data.zip", str(tmp_path)
    )
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert archive.read("table.csv") == b"name,value\ntest,1\n"


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
        local_storage.ensure_local_file(
            "https://example.org/a.zip", str(tmp_path), lambda: True
        )
    file = tmp_path / "file"
    file.write_text("not a directory")
    with pytest.raises(local_storage.DownloadError, match="保存"):
        local_storage.ensure_local_file("https://example.org/a.zip", str(file))


@pytest.mark.parametrize("nested", [False, True])
def test_project_can_move_with_downloaded_archives(
    qgis_app, qgis_new_project, tmp_path, nested
):
    from qgis.core import QgsProject, QgsVectorLayer
    from ksj import zip_scanner

    original = tmp_path / "original"
    original.mkdir()
    archive = original / "data.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as output:
        output.writestr("table.csv", "name,value\ntest,1\n")
    if nested:
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("inner.zip", buffer.getvalue())
    else:
        archive.write_bytes(buffer.getvalue())
    root = zip_scanner.vsi_zip_root(str(archive))
    if nested:
        root = zip_scanner.nested_zip_root(root, "inner.zip")
    layer = QgsVectorLayer(root + "/table.csv", "table", "ogr")
    assert layer.isValid()
    project = QgsProject.instance()
    project.addMapLayer(layer)
    assert project.write(str(original / "test.qgz"))
    project.clear()
    if nested:
        # QGIS 3.xは入れ子VSIを相対パス化しない。同じ共有パスでの再読込を保証する。
        assert project.read(str(original / "test.qgz"))
        restored = list(project.mapLayers().values())[0]
        assert restored.isValid() and restored.featureCount() == 1
        assert str(original) in restored.source()
        return
    moved = tmp_path / "shared"
    original.rename(moved)
    assert project.read(str(moved / "test.qgz"))
    restored = list(project.mapLayers().values())[0]
    assert restored.isValid() and restored.featureCount() == 1


def test_browser_model_first_selection_refreshes_to_local_layers(
    qgis_app, qgis_new_project, storage_settings, tmp_path, monkeypatch
):
    from qgis.core import QgsBrowserModel, QgsProject
    from ksj.browser import KsjDataItemProvider, KsjRootItem
    from ksj.catalog_browser import KsjResourceItem

    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("table.csv", "name,value\ntest,1\n")
    calls = []

    def download(url, directory):
        calls.append((url, directory))
        target = Path(directory) / "data.zip"
        target.write_bytes(archive.read_bytes())
        return str(target)

    monkeypatch.setattr(local_storage, "ensure_local_file", download)
    monkeypatch.setattr(
        local_storage.QFileDialog,
        "getExistingDirectory",
        lambda *args: str(storage_settings),
    )

    class Root(KsjRootItem):
        def createChildren(self):
            return [
                KsjResourceItem(
                    self,
                    "/ksj/test",
                    {"filename": "data.zip", "url": "https://example.org/data.zip"},
                )
            ]

    class Provider(KsjDataItemProvider):
        def createDataItem(self, path, parent):
            return Root() if path == "" else None

    def wait_for(predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            qgis_app.processEvents()
            time.sleep(0.01)
        assert predicate()

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
        choice = model.dataItem(model.index(0, 0, resource))
        assert "保存先" in choice.name() and calls == []
        assert choice.handleDoubleClick()
        wait_for(lambda: model.data(model.index(0, 0, resource)) == "table.csv")
        assert calls == [("https://example.org/data.zip", str(storage_settings))]
        layer_item = model.dataItem(model.index(0, 0, resource))
        assert "/vsicurl/" not in layer_item.mimeUris()[0].uri
        assert layer_item.handleDoubleClick()
        existing_layer = list(QgsProject.instance().mapLayers().values())[0]
        old_source = existing_layer.source()
        changed = tmp_path / "新しい保存先"
        monkeypatch.setattr(
            local_storage.QFileDialog,
            "getExistingDirectory",
            lambda *args: str(changed),
        )
        change_action = next(
            action
            for action in model.dataItem(resource).actions(None)
            if "保存先" in action.text() and "変更" in action.text()
        )
        change_action.trigger()
        wait_for(
            lambda: len(calls) == 2
            and model.rowCount(resource) > 0
            and str(changed)
            in model.dataItem(model.index(0, 0, resource)).mimeUris()[0].uri
        )
        updated = model.dataItem(model.index(0, 0, resource))
        assert str(changed) in updated.mimeUris()[0].uri
        assert (
            existing_layer.source() == old_source and existing_layer.featureCount() == 1
        )
    finally:
        model.removeRootItems()
        registry.removeProvider(provider)
        qgis_app.processEvents()
