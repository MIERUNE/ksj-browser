"""ZIP閲覧・選択取得・追加方法の記憶を実HTTPと実QGISで検証する。"""

import zipfile
from pathlib import Path

import pytest
from osgeo import ogr, osr
from qgis.core import QgsProject, QgsSettings
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication, QRadioButton

from ksj import catalog_browser, local_storage
from tests.helpers import point_geojson, pump_until, zip_bytes
from tests.test_local_storage import run_workers


@pytest.fixture
def preferences(qgis_app, monkeypatch, tmp_path):
    monkeypatch.setattr(local_storage, "DIRECTORY_KEY", "ksj-tests/lazy-directory")
    monkeypatch.setattr(local_storage, "MODE_KEY", "ksj-tests/lazy-mode")
    for key in (local_storage.DIRECTORY_KEY, local_storage.MODE_KEY):
        QgsSettings().remove(key)
    yield tmp_path / "saved"
    for key in (local_storage.DIRECTORY_KEY, local_storage.MODE_KEY):
        QgsSettings().remove(key)


def resource(http_data):
    return catalog_browser.KsjResourceItem(
        None, "/test/lazy", {"filename": "data.zip", "url": http_data["url"]}
    )


def listing(qgis_app, http_data):
    item = resource(http_data)

    def create():
        children = item.createChildren()
        for child in children:
            child.setParent(None)
            child.moveToThread(qgis_app.thread())
        return children

    return run_workers(qgis_app, [create])[0]


def finish(qgis_app):
    from ksj import layer_loading

    pump_until(qgis_app, lambda: not layer_loading.pending, timeout=15)


def archive_with_unselected_data(http_data):
    http_data.update(
        range_support=True,
        body=zip_bytes(
            [
                ("point.geojson", point_geojson()),
                ("unselected.bin", b"z" * 2_000_000),
            ]
        ),
    )


def test_expand_lists_files_without_save_directory_or_data_download(
    qgis_app, preferences, http_data
):
    archive_with_unselected_data(http_data)
    children = listing(qgis_app, http_data)
    assert [child.name() for child in children] == ["point.geojson"]
    assert not preferences.exists()
    assert http_data["bytes_sent"] < 70_000
    assert all(http_data["ranges"])


def test_repeated_range_requests_keep_reply_alive(qgis_app, preferences, http_data):
    import gc
    from ksj import remote_zip

    archive_with_unselected_data(http_data)

    def repeat():
        for _ in range(30):
            gc.collect()
            assert remote_zip.list_members(http_data["url"]) == [
                "point.geojson",
                "unselected.bin",
            ]

    run_workers(qgis_app, [repeat])


def test_canceled_worker_can_finish_without_gui_event_processing(
    qgis_app, preferences, http_data
):
    import threading
    from qgis.PyQt.QtCore import Qt
    from ksj import remote_zip

    canceled, queued, errors = threading.Event(), threading.Event(), []

    def mark_queued(job):
        queued.set()

    def request():
        try:
            remote_zip.list_members(http_data["url"], is_canceled=canceled.is_set)
        except local_storage.DownloadCanceled:
            errors.append("canceled")

    signal = remote_zip._range_requests.requested
    signal.connect(mark_queued, Qt.ConnectionType.DirectConnection)
    try:
        worker = threading.Thread(target=request)
        worker.start()
        assert queued.wait(2)
        canceled.set()
        worker.join(timeout=2)  # GUIイベントを処理せず、QGIS終了時の待機を再現。
    finally:
        signal.disconnect(mark_queued)
    assert not worker.is_alive()
    assert errors == ["canceled"]
    qgis_app.processEvents()
    assert not http_data["requests"]


def test_non_range_server_does_not_silently_download_and_extract(
    qgis_app, preferences, http_data
):
    preferences.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(preferences))
    children = listing(qgis_app, http_data)
    assert "部分取得" in children[0].name()
    assert not list(preferences.iterdir())
    assert all(http_data["ranges"])


def test_double_click_saves_only_selection_and_reopens_offline(
    qgis_app, qgis_new_project, preferences, http_data, tmp_path
):
    archive_with_unselected_data(http_data)
    preferences.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(preferences))
    children = listing(qgis_app, http_data)
    assert not list(preferences.iterdir())
    assert children[0].handleDoubleClick()
    finish(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1 and layers[0].featureCount() == 1
    assert next(layers[0].getFeatures())["name"] == "試験ダム"
    assert Path(layers[0].source()).is_file()
    assert not list(preferences.rglob("unselected.bin"))
    assert http_data["bytes_sent"] < 140_000
    path = tmp_path / "saved.qgz"
    assert QgsProject.instance().write(str(path))
    QgsProject.instance().clear()
    http_data["status"] = 503
    before = len(http_data["requests"])
    assert QgsProject.instance().read(str(path))
    assert list(QgsProject.instance().mapLayers().values())[0].featureCount() == 1
    assert listing(qgis_app, http_data)[0].handleDoubleClick()
    finish(qgis_app)
    assert len(http_data["requests"]) == before


def test_setting_change_applies_to_already_visible_item(
    qgis_app, qgis_new_project, preferences, http_data
):
    archive_with_unselected_data(http_data)
    item = listing(qgis_app, http_data)[0]
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    assert item.handleDoubleClick()
    finish(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1
    assert layers[0].providerType() == "memory"
    assert next(layers[0].getFeatures())["name"] == "試験ダム"
    assert layers[0].crs().authid() == "EPSG:4326"
    assert not preferences.exists()
    preferences.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(preferences))
    QgsSettings().setValue(local_storage.MODE_KEY, "save")
    assert item.handleDoubleClick()
    finish(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert {layer.providerType() for layer in layers} == {"ogr", "memory"}


def test_settings_dialog_remembers_temporary_and_cancel_is_atomic(preferences):
    original = str(preferences)
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, original)

    def accept_temporary():
        dialog = QApplication.activeModalWidget()
        buttons = dialog.findChildren(QRadioButton)
        next(button for button in buttons if "一時" in button.text()).setChecked(True)
        dialog.accept()

    QTimer.singleShot(0, accept_temporary)
    assert local_storage.configure_loading()
    assert local_storage.loading_mode() == "temporary"
    assert local_storage.download_directory() == original

    def cancel_save():
        dialog = QApplication.activeModalWidget()
        next(
            button
            for button in dialog.findChildren(QRadioButton)
            if "フォルダ" in button.text()
        ).setChecked(True)
        dialog.reject()

    QTimer.singleShot(0, cancel_save)
    assert not local_storage.configure_loading()
    assert local_storage.loading_mode() == "temporary"
    assert not preferences.exists()


def test_shapefile_selection_keeps_sidecars_and_other_folders_separate(
    qgis_app, preferences, http_data, tmp_path
):
    from ksj import remote_zip

    source = tmp_path / "source"
    source.mkdir()
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(6677)
    dataset = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(str(source))
    layer = dataset.CreateLayer(
        "point", srs=crs, geom_type=ogr.wkbPoint, options=["ENCODING=UTF-8"]
    )
    layer.CreateField(ogr.FieldDefn("name", ogr.OFTString))
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetField("name", "試験地点")
    feature.SetGeometry(ogr.CreateGeometryFromWkt("POINT (100 200)"))
    layer.CreateFeature(feature)
    feature = layer = dataset = None
    http_data.update(
        range_support=True,
        body=zip_bytes(
            [(f"area/{p.name}", p.read_bytes()) for p in source.iterdir()]
            + [("other/point.shp", b"unrelated"), ("extra.bin", b"z" * 1_000_000)]
        ),
    )
    preferences.mkdir()
    path = run_workers(
        qgis_app,
        [
            lambda: remote_zip.ensure_member(
                http_data["url"], "area/point.shp", str(preferences)
            )
        ],
    )[0]
    from qgis.core import QgsVectorLayer

    result = QgsVectorLayer(path, "test", "ogr")
    assert result.isValid() and result.featureCount() == 1
    assert next(result.getFeatures())["name"] == "試験地点"
    assert result.crs().authid() == "EPSG:6677"
    assert {p.suffix for p in Path(path).parent.iterdir()} >= {
        ".shp",
        ".shx",
        ".dbf",
        ".prj",
        ".cpg",
    }
    assert not list(preferences.rglob("extra.bin"))
    assert not list(preferences.rglob("other"))


@pytest.mark.parametrize("name", ["../escape.shp", "/absolute.shp", "C:/bad.shp"])
def test_unsafe_zip_names_never_create_files(qgis_app, preferences, http_data, name):
    http_data.update(range_support=True, body=zip_bytes([(name, "bad")]))
    children = listing(qgis_app, http_data)
    assert "安全" in children[0].name()
    assert not preferences.exists()


def test_compressed_member_crc_failure_is_not_cached(qgis_app, preferences, http_data):
    from ksj import remote_zip

    data = bytearray(
        zip_bytes(
            [("point.geojson", point_geojson())], compression=zipfile.ZIP_DEFLATED
        )
    )
    data[30 + len("point.geojson")] = 7
    http_data.update(range_support=True, body=bytes(data))
    preferences.mkdir()
    with pytest.raises(local_storage.DownloadError):
        run_workers(
            qgis_app,
            [
                lambda: remote_zip.ensure_member(
                    http_data["url"], "point.geojson", str(preferences)
                )
            ],
        )
    assert not list(preferences.rglob("point.geojson"))
    assert not list(preferences.rglob("*.part"))


def test_japanese_member_names_are_saved_and_browsed_offline(
    qgis_app, preferences, http_data
):
    from ksj import remote_zip

    http_data.update(
        range_support=True, body=zip_bytes([("北海道/地点.geojson", point_geojson())])
    )
    preferences.mkdir()
    path = run_workers(
        qgis_app,
        [
            lambda: remote_zip.ensure_member(
                http_data["url"], "北海道/地点.geojson", str(preferences)
            )
        ],
    )[0]
    assert Path(path).is_file()
    http_data["status"] = 503
    assert remote_zip.list_members(http_data["url"], str(preferences)) == [
        "北海道/地点.geojson"
    ]


def test_nested_zip_expansion_never_reads_its_payload(qgis_app, preferences, http_data):
    inner = zip_bytes([("point.geojson", point_geojson())])
    http_data.update(range_support=True, body=zip_bytes([("inner.ZIP", inner)]))
    child = listing(qgis_app, http_data)[0]
    before = list(http_data["ranges"])
    assert "本体取得" in child.createChildren()[0].name()
    assert http_data["ranges"] == before


def test_drag_fetches_nothing_until_drop_and_uses_temporary_preference(
    qgis_app, qgis_new_project, preferences, http_data
):
    from ksj import layer_loading

    archive_with_unselected_data(http_data)
    item = listing(qgis_app, http_data)[0]
    before = list(http_data["requests"])
    uri = item.mimeUris()[0]
    assert http_data["requests"] == before
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    handler = layer_loading.KsjDropHandler()
    assert handler.customUriProviderKey() == uri.providerKey
    assert handler.handleCustomUriCanvasDrop(uri, None)
    finish(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1 and layers[0].providerType() == "memory"
    assert not preferences.exists()


def test_temporary_raster_keeps_file_until_layer_is_removed(
    qgis_app, qgis_new_project, preferences, http_data, tmp_path
):
    from tests.helpers import make_raster

    source = make_raster(tmp_path / "image.tif")
    http_data.update(
        range_support=True, body=zip_bytes([("image.tif", source.read_bytes())])
    )
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    assert listing(qgis_app, http_data)[0].handleDoubleClick()
    finish(qgis_app)
    layer = list(QgsProject.instance().mapLayers().values())[0]
    path = Path(layer.source())
    assert path.is_file() and layer.isValid()
    assert layer.dataProvider().sample(layer.extent().center(), 1)[0] == 7
    QgsProject.instance().removeMapLayer(layer.id())
    qgis_app.processEvents()
    assert not path.exists()
    assert not preferences.exists()


def test_browser_displays_current_preference_and_updates_after_dialog(
    qgis_app, preferences
):
    from ksj.browser import KsjRootItem

    root = KsjRootItem()
    item = root.createChildren()[0]
    assert "保存先未設定" in item.name()

    def choose_temporary():
        dialog = QApplication.activeModalWidget()
        dialog.temporary.setChecked(True)
        dialog.accept()

    QTimer.singleShot(0, choose_temporary)
    assert item.handleDoubleClick()
    qgis_app.processEvents()
    assert "一時レイヤー" in item.name()
    assert "保存しない" in item.toolTip()

    def choose_save():
        dialog = QApplication.activeModalWidget()
        dialog.save.setChecked(True)
        dialog.directory.setText(str(preferences))
        dialog.accept()

    QTimer.singleShot(0, choose_save)
    action = next(a for a in root.actions(None) if "設定" in a.text())
    action.trigger()
    qgis_app.processEvents()
    assert "保存して追加" in item.name()
    assert str(preferences) in item.name()


def test_browser_worker_created_settings_row_updates_on_gui(qgis_app, preferences):
    from qgis.core import QgsApplication, QgsBrowserModel
    from ksj.browser import KsjDataItemProvider

    registry = QgsApplication.dataItemProviderRegistry()
    provider = KsjDataItemProvider()
    registry.addProvider(provider)
    model = QgsBrowserModel()
    try:
        model.initialize()
        root = model.findPath("/ksj")
        model.fetchMore(root)
        pump_until(qgis_app, lambda: model.rowCount(root) > 0, timeout=5)
        item = next(
            model.dataItem(model.index(row, 0, root))
            for row in range(model.rowCount(root))
            if isinstance(
                model.dataItem(model.index(row, 0, root)),
                catalog_browser.KsjLoadingSettingsItem,
            )
        )
        assert item.thread() == qgis_app.thread()
        QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
        local_storage.loading_settings_signals.changed.emit()
        pump_until(qgis_app, lambda: "一時レイヤー" in item.name(), timeout=1)
    finally:
        model.removeRootItems()
        registry.removeProvider(provider)
        qgis_app.processEvents()


def test_browser_model_lists_remote_zip_and_adds_selected_layer(
    qgis_app, qgis_new_project, preferences, http_data
):
    from qgis.core import QgsApplication, QgsBrowserModel
    from ksj.browser import KsjDataItemProvider, KsjRootItem

    archive_with_unselected_data(http_data)
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")

    class Root(KsjRootItem):
        def createChildren(self):
            return [resource(http_data)]

    class Provider(KsjDataItemProvider):
        def createDataItem(self, path, parent):
            return Root() if path == "" else None

    registry = QgsApplication.dataItemProviderRegistry()
    provider = Provider()
    registry.addProvider(provider)
    model = QgsBrowserModel()
    try:
        model.initialize()
        root = model.findPath("/ksj")
        model.fetchMore(root)
        pump_until(qgis_app, lambda: model.rowCount(root) > 0, timeout=5)
        archive = model.index(0, 0, root)
        model.fetchMore(archive)
        pump_until(qgis_app, lambda: model.rowCount(archive) > 0, timeout=10)
        item = model.dataItem(model.index(0, 0, archive))
        assert item.name() == "point.geojson"
        assert not preferences.exists() and http_data["bytes_sent"] < 70_000
        assert item.handleDoubleClick()
        finish(qgis_app)
        layer = next(iter(QgsProject.instance().mapLayers().values()))
        assert layer.providerType() == "memory" and layer.featureCount() == 1
        assert not preferences.exists()
    finally:
        model.removeRootItems()
        registry.removeProvider(provider)
        qgis_app.processEvents()


def test_cancel_selection_does_not_leave_cache_and_can_retry(
    qgis_app, preferences, http_data
):
    from ksj import remote_zip

    preferences.mkdir()
    archive_with_unselected_data(http_data)
    with pytest.raises(local_storage.DownloadCanceled):
        run_workers(
            qgis_app,
            [
                lambda: remote_zip.ensure_member(
                    http_data["url"],
                    "point.geojson",
                    str(preferences),
                    is_canceled=lambda: bool(list(preferences.rglob("point.geojson"))),
                )
            ],
        )
    assert not list(preferences.rglob("point.geojson"))
    assert not list(preferences.rglob("*.part"))
    path = run_workers(
        qgis_app,
        [
            lambda: remote_zip.ensure_member(
                http_data["url"], "point.geojson", str(preferences)
            )
        ],
    )[0]
    assert Path(path).is_file()


def test_cancel_task_prevents_late_layer_addition(
    qgis_app, qgis_new_project, preferences, http_data
):
    from ksj import layer_loading

    archive_with_unselected_data(http_data)
    item = listing(qgis_app, http_data)[0]
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    http_data["delay"] = 0.1
    item.handleDoubleClick()
    task = next(iter(layer_loading.pending.values()))
    done = []
    task.taskTerminated.connect(lambda: done.append(True))
    layer_loading.cancel_pending()
    pump_until(qgis_app, lambda: bool(done), timeout=10)
    qgis_app.processEvents()
    assert not QgsProject.instance().mapLayers()
    assert not preferences.exists()


def test_temporary_materialization_runs_in_worker_and_returns_gui_owned_layer(
    qgis_app, qgis_new_project, preferences, http_data, monkeypatch
):
    from qgis.core import QgsVectorLayer
    from qgis.PyQt.QtCore import QThread

    archive_with_unselected_data(http_data)
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    threads = []
    original = QgsVectorLayer.materialize

    def record(self, request, feedback=None):
        threads.append(QThread.currentThread())
        assert feedback is not None
        return original(self, request, feedback)

    monkeypatch.setattr(QgsVectorLayer, "materialize", record)
    assert listing(qgis_app, http_data)[0].handleDoubleClick()
    finish(qgis_app)
    assert len(threads) == 1 and threads[0] != qgis_app.thread()
    layer = list(QgsProject.instance().mapLayers().values())[0]
    assert layer.thread() == qgis_app.thread()
    assert layer.featureCount() == 1


@pytest.mark.parametrize("driver,suffix", [("GPKG", ".gpkg"), ("GML", ".gml")])
@pytest.mark.parametrize("mode", ["save", "temporary"])
def test_multilayer_file_is_inspected_only_when_added(
    qgis_app, qgis_new_project, preferences, http_data, tmp_path, driver, suffix, mode
):
    source = tmp_path / "source"
    source.mkdir()
    path = source / ("multiple" + suffix)
    data = ogr.GetDriverByName(driver).CreateDataSource(str(path))
    for name in ("rivers", "stations"):
        layer = data.CreateLayer(name, geom_type=ogr.wkbPoint)
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(ogr.CreateGeometryFromWkt("POINT (140 40)"))
        layer.CreateFeature(feature)
        feature = layer = None
    data = None
    http_data.update(
        range_support=True,
        body=zip_bytes([(p.name, p.read_bytes()) for p in source.iterdir()]),
    )
    preferences.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(preferences))
    QgsSettings().setValue(local_storage.MODE_KEY, mode)
    children = listing(qgis_app, http_data)
    assert len(children) == 1 and not list(preferences.iterdir())
    assert children[0].handleDoubleClick()
    finish(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert {layer.name() for layer in layers} == {"rivers", "stations"}
    assert all(layer.featureCount() == 1 for layer in layers)
    assert {layer.providerType() for layer in layers} == {
        "memory" if mode == "temporary" else "ogr"
    }


def test_sublayer_query_failure_can_retry_same_item(
    qgis_app, qgis_new_project, preferences, http_data, tmp_path, monkeypatch
):
    from ksj import layer_loading
    from qgis.core import QgsProviderRegistry
    from types import SimpleNamespace
    from tests.helpers import make_gpkg

    path = make_gpkg(tmp_path / "data.gpkg", ["rivers"])
    http_data.update(
        range_support=True, body=zip_bytes([("data.gpkg", path.read_bytes())])
    )
    preferences.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(preferences))
    provider = QgsProviderRegistry.instance().providerMetadata("ogr")
    original = provider.querySublayers
    calls, errors = [], []

    def query(*args):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("一時的な列挙失敗")
        return original(*args)

    registry = SimpleNamespace(
        providerMetadata=lambda key: SimpleNamespace(querySublayers=query)
    )
    monkeypatch.setattr(
        layer_loading, "QgsProviderRegistry", SimpleNamespace(instance=lambda: registry)
    )
    monkeypatch.setattr(
        layer_loading, "notify", lambda message, **kwargs: errors.append(message)
    )
    item = listing(qgis_app, http_data)[0]
    item.handleDoubleClick()
    finish(qgis_app)
    assert not QgsProject.instance().mapLayers()
    assert "一時的な列挙失敗" in errors[0]
    before = len(http_data["requests"])
    item.handleDoubleClick()
    finish(qgis_app)
    assert {layer.name() for layer in QgsProject.instance().mapLayers().values()} == {
        "rivers"
    }
    assert len(http_data["requests"]) == before
