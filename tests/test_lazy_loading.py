"""ZIP閲覧・選択取得・追加方法の記憶を実HTTPと実QGISで検証する。"""

import gc
import tempfile
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from osgeo import ogr, osr
from qgis.core import (
    QgsApplication,
    QgsBrowserModel,
    QgsDataItem,
    QgsProject,
    QgsProviderRegistry,
    QgsSettings,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QApplication, QMenu, QRadioButton

from ksj import (
    catalog_browser,
    layer_loading,
    local_storage,
    remote_zip,
    temporary_files,
)
from ksj.browser import KsjDataItemProvider, KsjRootItem
from tests.helpers import (
    make_raster,
    make_shapefile,
    shapefile_entries,
    make_vector,
    point_geojson,
    pump_until,
    run_workers,
    termination_of,
    wait_for_layer_loading,
    workspaces,
    zip_bytes,
)


def source_path(layer):
    """参照先ファイル。サブレイヤーの source "パス|layername=名前" からもパスだけ取り出す。"""
    return Path(layer.source().split("|")[0])


def stored_in(layer, directory):
    """レイヤーの参照先が、指定した保存先フォルダの配下にあるか。"""
    return directory in source_path(layer).parents


@pytest.fixture
def logged(monkeypatch):
    """一時ディレクトリ削除の警告ログを (本文, warning) の組で集める。"""
    messages = []
    monkeypatch.setattr(
        temporary_files,
        "log_message",
        lambda message, warning=False: messages.append((message, warning)),
    )
    return messages


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


def fetch(qgis_app, http_data, directory, member, **options):
    """ワーカーで選択取得を1回実行し、保存したファイルのパスを返す。"""
    return run_workers(
        qgis_app,
        [
            lambda: remote_zip.ensure_member(
                http_data["url"], member, str(directory), **options
            )
        ],
    )[0]


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
    qgis_app, storage_settings, http_data
):
    archive_with_unselected_data(http_data)
    children = listing(qgis_app, http_data)
    assert [child.name() for child in children] == ["point.geojson"]
    assert not storage_settings.exists()
    assert http_data["bytes_sent"] < 70_000
    assert all(http_data["ranges"])


def test_repeated_range_requests_keep_reply_alive(
    qgis_app, storage_settings, http_data
):
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
    qgis_app, storage_settings, http_data
):
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
    qgis_app, storage_settings, http_data
):
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    children = listing(qgis_app, http_data)
    assert "部分取得" in children[0].name()
    assert not list(storage_settings.iterdir())
    assert all(http_data["ranges"])


def test_double_click_saves_only_selection_and_reopens_offline(
    qgis_app, qgis_new_project, storage_settings, http_data, tmp_path
):
    archive_with_unselected_data(http_data)
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    children = listing(qgis_app, http_data)
    assert not list(storage_settings.iterdir())
    assert children[0].handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1 and layers[0].featureCount() == 1
    assert next(layers[0].getFeatures())["name"] == "試験ダム"
    assert source_path(layers[0]).is_file()
    assert not list(storage_settings.rglob("unselected.bin"))
    assert http_data["bytes_sent"] < 140_000
    path = tmp_path / "saved.qgz"
    assert QgsProject.instance().write(str(path))
    QgsProject.instance().clear()
    http_data["status"] = 503
    before = len(http_data["requests"])
    assert QgsProject.instance().read(str(path))
    assert list(QgsProject.instance().mapLayers().values())[0].featureCount() == 1
    assert listing(qgis_app, http_data)[0].handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    assert len(http_data["requests"]) == before


def test_setting_change_applies_to_already_visible_item(
    qgis_app, qgis_new_project, storage_settings, http_data
):
    archive_with_unselected_data(http_data)
    item = listing(qgis_app, http_data)[0]
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    assert item.handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1
    assert layers[0].providerType() == "ogr"
    assert source_path(layers[0]).is_file()
    assert not stored_in(layers[0], storage_settings)
    assert next(layers[0].getFeatures())["name"] == "試験ダム"
    assert layers[0].crs().authid() == "EPSG:4326"
    assert not storage_settings.exists()
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    QgsSettings().setValue(local_storage.MODE_KEY, "save")
    assert item.handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 2
    assert {layer.providerType() for layer in layers} == {"ogr"}
    assert {stored_in(layer, storage_settings) for layer in layers} == {True, False}


@pytest.mark.parametrize("mode", ["save", "temporary"])
def test_file_context_menu_adds_selected_layer_using_current_settings(
    qgis_app, qgis_new_project, storage_settings, http_data, mode
):
    archive_with_unselected_data(http_data)
    item = listing(qgis_app, http_data)[0]
    before = list(http_data["requests"])
    menu = QMenu()
    menu.addActions(item.actions(menu))
    assert [action.text() for action in menu.actions()] == [
        "レイヤをプロジェクトに追加"
    ]
    # 標準レイヤー用の追加・プロパティメニューを自動生成させない。
    assert item.type() == QgsDataItem.Type.Custom
    assert http_data["requests"] == before
    assert not storage_settings.exists()

    # メニューを開いた後の設定変更も、実行時に反映する。
    QgsSettings().setValue(local_storage.MODE_KEY, mode)
    if mode == "save":
        storage_settings.mkdir()
        QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    menu.actions()[0].trigger()
    wait_for_layer_loading(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1
    layer = layers[0]
    assert layer.isValid() and layer.featureCount() == 1
    assert next(layer.getFeatures())["name"] == "試験ダム"
    assert layer.providerType() == "ogr"
    assert source_path(layer).is_file()
    assert stored_in(layer, storage_settings) == (mode == "save")
    if mode == "temporary":
        assert not storage_settings.exists()
    assert not list(storage_settings.rglob("unselected.bin"))
    assert http_data["bytes_sent"] < 140_000


def test_settings_dialog_remembers_temporary_and_cancel_is_atomic(storage_settings):
    original = str(storage_settings)
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
    assert not storage_settings.exists()


def test_shapefile_selection_keeps_sidecars_and_other_folders_separate(
    qgis_app, storage_settings, http_data, tmp_path
):
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
    storage_settings.mkdir()
    path = fetch(qgis_app, http_data, storage_settings, "area/point.shp")
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
    assert not list(storage_settings.rglob("extra.bin"))
    assert not list(storage_settings.rglob("other"))


@pytest.mark.parametrize("concurrent", [False, True])
def test_selections_share_distribution_root_and_preserve_zip_paths(
    qgis_app, storage_settings, http_data, concurrent
):
    entries = [
        ("point.geojson", point_geojson()),
        ("0101/point.geojson", point_geojson("別の地点")),
        ("data/point.geojson", point_geojson("配布名と同じフォルダ")),
        ("unselected.geojson", point_geojson()),
    ]
    http_data.update(range_support=True, body=zip_bytes(entries))
    storage_settings.mkdir()
    jobs = [
        lambda name=name: remote_zip.ensure_member(
            http_data["url"], name, str(storage_settings)
        )
        for name, _ in entries[:3]
    ]
    paths = (
        run_workers(qgis_app, jobs)
        if concurrent
        else [run_workers(qgis_app, [job])[0] for job in jobs]
    )
    root = Path(paths[0]).parent
    assert root.parent == storage_settings
    assert root.name.startswith("data-")
    for path, (name, contents) in zip(paths, entries):
        assert Path(path) == root / name
        assert Path(path).read_text() == contents
    assert not (root / "unselected.geojson").exists()
    http_data["status"] = 503
    before = len(http_data["requests"])
    assert remote_zip.list_members(http_data["url"], str(storage_settings)) == [
        name for name, _ in entries
    ]
    assert run_workers(qgis_app, jobs) == paths
    assert len(http_data["requests"]) == before


@pytest.mark.parametrize("full_first", [False, True])
def test_full_and_selected_downloads_share_paths(
    qgis_app, storage_settings, http_data, full_first
):
    archive_with_unselected_data(http_data)
    storage_settings.mkdir()

    def full():
        return Path(
            run_workers(
                qgis_app,
                [
                    lambda: local_storage.ensure_local_data(
                        http_data["url"], str(storage_settings)
                    )
                ],
            )[0]
        )

    def selected():
        return Path(fetch(qgis_app, http_data, storage_settings, "point.geojson"))

    if full_first:
        root = full()
        http_data["status"] = 503
        path = selected()
    else:
        path = selected()
        root = full()
    assert root.parent == storage_settings
    assert path == root / "point.geojson"
    assert path.read_text() == point_geojson()
    assert (root / "unselected.bin").is_file()
    assert set(remote_zip.list_members(http_data["url"], str(storage_settings))) == {
        "point.geojson",
        "unselected.bin",
    }


@pytest.mark.parametrize("name", ["../escape.shp", "/absolute.shp", "C:/bad.shp"])
def test_unsafe_zip_names_never_create_files(
    qgis_app, storage_settings, http_data, name
):
    http_data.update(range_support=True, body=zip_bytes([(name, "bad")]))
    children = listing(qgis_app, http_data)
    assert "安全" in children[0].name()
    assert not storage_settings.exists()


def test_compressed_member_crc_failure_is_not_cached(
    qgis_app, storage_settings, http_data
):
    data = bytearray(
        zip_bytes(
            [("point.geojson", point_geojson())], compression=zipfile.ZIP_DEFLATED
        )
    )
    data[30 + len("point.geojson")] = 7
    http_data.update(range_support=True, body=bytes(data))
    storage_settings.mkdir()
    with pytest.raises(local_storage.DownloadError):
        fetch(qgis_app, http_data, storage_settings, "point.geojson")
    assert not list(storage_settings.rglob("point.geojson"))
    assert not list(storage_settings.rglob("*.part"))


def test_japanese_member_names_are_saved_and_browsed_offline(
    qgis_app, storage_settings, http_data
):
    http_data.update(
        range_support=True, body=zip_bytes([("北海道/地点.geojson", point_geojson())])
    )
    storage_settings.mkdir()
    path = fetch(qgis_app, http_data, storage_settings, "北海道/地点.geojson")
    assert Path(path).is_file()
    http_data["status"] = 503
    assert remote_zip.list_members(http_data["url"], str(storage_settings)) == [
        "北海道/地点.geojson"
    ]


def test_nested_zip_expansion_never_reads_its_payload(
    qgis_app, storage_settings, http_data
):
    inner = zip_bytes([("point.geojson", point_geojson())])
    http_data.update(range_support=True, body=zip_bytes([("inner.ZIP", inner)]))
    child = listing(qgis_app, http_data)[0]
    before = list(http_data["ranges"])
    assert "本体取得" in child.createChildren()[0].name()
    assert http_data["ranges"] == before


def test_drag_fetches_nothing_until_drop_and_uses_temporary_preference(
    qgis_app, qgis_new_project, storage_settings, http_data
):
    archive_with_unselected_data(http_data)
    item = listing(qgis_app, http_data)[0]
    before = list(http_data["requests"])
    uri = item.mimeUris()[0]
    assert http_data["requests"] == before
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    handler = layer_loading.KsjDropHandler()
    assert handler.customUriProviderKey() == uri.providerKey
    assert handler.handleCustomUriCanvasDrop(uri, None)
    wait_for_layer_loading(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1 and layers[0].providerType() == "ogr"
    assert source_path(layers[0]).is_file()
    assert not storage_settings.exists()


def test_temporary_raster_keeps_file_until_layer_is_removed(
    qgis_app, qgis_new_project, storage_settings, http_data, tmp_path
):
    source = make_raster(tmp_path / "image.tif")
    http_data.update(
        range_support=True, body=zip_bytes([("image.tif", source.read_bytes())])
    )
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    assert listing(qgis_app, http_data)[0].handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layer = list(QgsProject.instance().mapLayers().values())[0]
    path = source_path(layer)
    assert path.is_file() and layer.isValid()
    assert layer.dataProvider().sample(layer.extent().center(), 1)[0] == 7
    QgsProject.instance().removeMapLayer(layer.id())
    qgis_app.processEvents()
    assert not path.exists()
    assert not storage_settings.exists()


def test_temporary_vector_keeps_file_until_layer_is_removed(
    qgis_app, qgis_new_project, storage_settings, http_data, temp_root
):
    archive_with_unselected_data(http_data)
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    assert listing(qgis_app, http_data)[0].handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layer = list(QgsProject.instance().mapLayers().values())[0]
    path = source_path(layer)
    assert layer.providerType() == "ogr" and path.is_file()
    assert next(layer.getFeatures())["name"] == "試験ダム"
    (workspace,) = workspaces(temp_root)
    assert workspace in path.parents
    QgsProject.instance().removeMapLayer(layer.id())
    qgis_app.processEvents()
    assert not path.exists()
    assert not workspaces(temp_root)
    assert not storage_settings.exists()


def test_temporary_sublayers_share_workspace_until_all_are_removed(
    qgis_app, qgis_new_project, storage_settings, http_data, tmp_path, temp_root
):
    source = make_vector(tmp_path / "multiple.gpkg", ["rivers", "stations"])
    http_data.update(
        range_support=True, body=zip_bytes([("multiple.gpkg", source.read_bytes())])
    )
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    assert listing(qgis_app, http_data)[0].handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert {layer.name() for layer in layers} == {"rivers", "stations"}
    path = source_path(layers[0])
    assert path.is_file() and len(workspaces(temp_root)) == 1
    QgsProject.instance().removeMapLayer(layers[0].id())
    qgis_app.processEvents()
    # 片方を閉じただけでは、残ったレイヤーのファイルを消さない。
    assert path.is_file() and len(workspaces(temp_root)) == 1
    assert layers[1].isValid() and layers[1].featureCount() == 1
    QgsProject.instance().removeMapLayer(layers[1].id())
    qgis_app.processEvents()
    assert not path.exists()
    assert not workspaces(temp_root)


def test_temporary_layer_reuses_saved_data_without_deleting_it(
    qgis_app, qgis_new_project, storage_settings, http_data, temp_root
):
    archive_with_unselected_data(http_data)
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    saved = Path(fetch(qgis_app, http_data, storage_settings, "point.geojson"))
    assert saved.is_file()
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    item = listing(qgis_app, http_data)[0]
    before = len(http_data["requests"])
    assert item.handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layer = list(QgsProject.instance().mapLayers().values())[0]
    # 保存済みの選択データを通信せず参照する。
    assert source_path(layer) == saved
    assert len(http_data["requests"]) == before
    QgsProject.instance().removeMapLayer(layer.id())
    qgis_app.processEvents()
    # 閉じても保存データは残り、空の一時ディレクトリだけが消える。
    assert saved.is_file()
    assert not workspaces(temp_root)


def test_browser_displays_current_preference_and_updates_after_dialog(
    qgis_app, storage_settings
):
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
        dialog.directory.setText(str(storage_settings))
        dialog.accept()

    QTimer.singleShot(0, choose_save)
    action = next(a for a in root.actions(None) if "設定" in a.text())
    action.trigger()
    qgis_app.processEvents()
    assert "保存して追加" in item.name()
    assert str(storage_settings) in item.name()


def test_browser_worker_created_settings_row_updates_on_gui(qgis_app, storage_settings):
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
    qgis_app, qgis_new_project, storage_settings, http_data
):
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
        file_index = model.index(0, 0, archive)
        item = model.dataItem(file_index)
        assert item.name() == "point.geojson"
        assert not storage_settings.exists() and http_data["bytes_sent"] < 70_000
        updates = []

        def record_update(first, last, roles):
            if first == file_index:
                updates.append(model.data(first))

        # 接続を残すとモデルが解放されず、後続テストの homePathChanged で落ちる。
        model.dataChanged.connect(record_update)
        try:
            assert item.handleDoubleClick()
            assert "読み込み中" in model.data(file_index)
            assert not model.hasChildren(file_index)
            wait_for_layer_loading(qgis_app)
            assert model.data(file_index) == "point.geojson"
            assert any("読み込み中" in text for text in updates)
            assert updates[-1] == "point.geojson"
        finally:
            model.dataChanged.disconnect(record_update)
        layer = next(iter(QgsProject.instance().mapLayers().values()))
        assert layer.providerType() == "ogr" and layer.featureCount() == 1
        assert not storage_settings.exists()
    finally:
        model.removeRootItems()
        registry.removeProvider(provider)
        qgis_app.processEvents()


def test_cancel_selection_does_not_leave_cache_and_can_retry(
    qgis_app, storage_settings, http_data
):
    storage_settings.mkdir()
    archive_with_unselected_data(http_data)
    with pytest.raises(local_storage.DownloadCanceled):
        fetch(
            qgis_app,
            http_data,
            storage_settings,
            "point.geojson",
            is_canceled=lambda: bool(list(storage_settings.rglob("point.geojson"))),
        )
    assert not list(storage_settings.rglob("point.geojson"))
    assert not list(storage_settings.rglob("*.part"))
    path = fetch(qgis_app, http_data, storage_settings, "point.geojson")
    assert Path(path).is_file()


def test_cancel_task_prevents_late_layer_addition(
    qgis_app, qgis_new_project, storage_settings, http_data, temp_root
):
    archive_with_unselected_data(http_data)
    item = listing(qgis_app, http_data)[0]
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    http_data["delay"] = 0.1
    item.handleDoubleClick()
    ended = termination_of(next(iter(layer_loading.pending.values())))
    layer_loading.cancel_pending()
    pump_until(qgis_app, ended, timeout=10)
    qgis_app.processEvents()
    assert not QgsProject.instance().mapLayers()
    assert not storage_settings.exists()
    assert not workspaces(temp_root)


def test_prepare_failure_keeps_original_error_when_cleanup_fails(
    monkeypatch, temp_root, logged
):
    def fail_download(*args):
        raise local_storage.DownloadError("取得に失敗しました")

    def fail_cleanup(self):
        raise OSError("使用中のため削除できません")

    monkeypatch.setattr(local_storage, "ensure_local_data", fail_download)
    monkeypatch.setattr(tempfile.TemporaryDirectory, "cleanup", fail_cleanup)
    task = SimpleNamespace(isCanceled=lambda: False, setProgress=lambda value: None)
    with pytest.raises(local_storage.DownloadError, match="取得に失敗しました"):
        layer_loading.prepare(
            task, "https://example.org/data.zip", "", "data", "temporary", ""
        )
    # 削除失敗はログ経路を通し、元の例外を置き換えない。本文と水準は _cleanup の試験が担う。
    assert len(logged) == 1


@pytest.mark.parametrize("driver,suffix", [("GPKG", ".gpkg"), ("GML", ".gml")])
@pytest.mark.parametrize("mode", ["save", "temporary"])
def test_multilayer_file_is_inspected_only_when_added(
    qgis_app,
    qgis_new_project,
    storage_settings,
    http_data,
    tmp_path,
    driver,
    suffix,
    mode,
):
    source = tmp_path / "source"
    source.mkdir()
    make_vector(source / ("multiple" + suffix), ["rivers", "stations"], driver=driver)
    http_data.update(
        range_support=True,
        body=zip_bytes([(p.name, p.read_bytes()) for p in source.iterdir()]),
    )
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    QgsSettings().setValue(local_storage.MODE_KEY, mode)
    children = listing(qgis_app, http_data)
    assert len(children) == 1 and not list(storage_settings.iterdir())
    assert children[0].handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert {layer.name() for layer in layers} == {"rivers", "stations"}
    assert all(layer.featureCount() == 1 for layer in layers)
    assert {layer.providerType() for layer in layers} == {"ogr"}
    assert all(
        stored_in(layer, storage_settings) == (mode == "save") for layer in layers
    )


def test_sublayer_query_failure_can_retry_same_item(
    qgis_app, qgis_new_project, storage_settings, http_data, tmp_path, monkeypatch
):
    path = make_vector(tmp_path / "data.gpkg", ["rivers"])
    http_data.update(
        range_support=True, body=zip_bytes([("data.gpkg", path.read_bytes())])
    )
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
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
    wait_for_layer_loading(qgis_app)
    assert not QgsProject.instance().mapLayers()
    assert "一時的な列挙失敗" in errors[0]
    before = len(http_data["requests"])
    item.handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    assert {layer.name() for layer in QgsProject.instance().mapLayers().values()} == {
        "rivers"
    }
    assert len(http_data["requests"]) == before


def test_replaced_task_drops_result_and_leaves_no_workspace(
    qgis_app, qgis_new_project, storage_settings, http_data, temp_root
):
    archive_with_unselected_data(http_data)
    item = listing(qgis_app, http_data)[0]
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    http_data["delay"] = 0.1
    item.handleDoubleClick()
    key, task = next(iter(layer_loading.pending.items()))
    ended = termination_of(task)
    # 取消を伴わず別のタスクに置き換えられた場合も、結果を捨てて一時ファイルを残さない。
    layer_loading.pending[key] = object()
    try:
        pump_until(qgis_app, ended, timeout=15)
        qgis_app.processEvents()
        assert not QgsProject.instance().mapLayers()
        assert not workspaces(temp_root)
    finally:
        layer_loading.pending.clear()
        layer_loading.loading_signals.changed.emit()


def test_temporary_workspace_is_removed_when_no_layer_can_be_added(
    qgis_app, qgis_new_project, storage_settings, http_data, temp_root, monkeypatch
):
    archive_with_unselected_data(http_data)
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    errors = []
    monkeypatch.setattr(
        layer_loading, "notify", lambda message, **kwargs: errors.append(message)
    )
    monkeypatch.setattr(
        layer_loading,
        "QgsVectorLayer",
        lambda source, title, provider: QgsVectorLayer("", title, provider),
    )
    assert listing(qgis_app, http_data)[0].handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    assert not QgsProject.instance().mapLayers()
    assert errors and "読み込めないレイヤー" in errors[0]
    assert not workspaces(temp_root)


@pytest.mark.parametrize("mode", ["save", "temporary"])
def test_shapefile_without_cpg_is_added_with_detected_encoding(
    qgis_app, qgis_new_project, storage_settings, http_data, tmp_path, mode
):
    source = make_shapefile(tmp_path / "city.shp", ["札幌市中央区"], "cp932")
    http_data.update(range_support=True, body=zip_bytes(shapefile_entries(source)))
    QgsSettings().setValue(local_storage.MODE_KEY, mode)
    if mode == "save":
        storage_settings.mkdir()
        QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    (item,) = listing(qgis_app, http_data)
    assert item.handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    (layer,) = QgsProject.instance().mapLayers().values()
    assert layer.dataProvider().encoding() == "Shift_JIS"
    assert next(layer.getFeatures())["name"] == "札幌市中央区"
