"""メッシュから配布データを探して追加する操作を実QGISで検証する。"""

import contextlib
from functools import partial
import json
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
import zipfile

import pytest
from osgeo import gdal
from qgis import utils
from qgis.core import (
    QgsBrowserModel,
    QgsBrowserProxyModel,
    QgsDataCollectionItem,
    QgsDataItem,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsSettings,
    QgsTask,
    QgsVectorLayer,
)
from qgis.gui import QgsActionMenu, QgsGui, QgsMapLayerActionContext
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QInputDialog,
    QListWidget,
)

from ksj import catalog, catalog_browser, local_storage, mesh_index, temporary_files
from ksj.browser import KsjDataItemProvider
from tests.helpers import (
    SHIFT_JIS_NAMES,
    make_raster,
    make_shapefile,
    make_vector,
    message_log_signal,
    mock_download,
    point_file,
    pump_until,
    shapefile_entries,
    stored_in,
    workspaces,
    zip_bytes,
)


@pytest.fixture(autouse=True)
def without_gui_interface(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "iface", None)
    monkeypatch.setattr(local_storage, "download_directory", lambda: str(tmp_path))


@contextlib.contextmanager
def registered_action():
    action = mesh_index.MeshIndexAction()
    action.register()
    try:
        yield action
    finally:
        action.unregister()


@pytest.fixture
def mesh_action(qgis_app):
    with registered_action() as action:
        yield action


def road_resources():
    return catalog.load_dataset("gml_datalist_KsjTmplt-N13-2024")["resources"]


def mesh_year_item(parent=None):
    """メッシュ配布が2件ある年度項目。索引の追加には親が要り、呼び出し側で保持する。"""
    resources = [r for r in road_resources() if r["region"] in {"5339", "5439"}]
    return catalog_browser.KsjResourceGroupItem(
        parent, "2024年", "/roads/2024", resources, ("region",), dimension="year"
    )


def wait_for_loads(app):
    pump_until(app, lambda: not mesh_index._pending, timeout=10)


def loaded_layers(exclude=None):
    """プロジェクトのレイヤーを、指定したレイヤーを除いて名前順に並べる。"""
    return sorted(
        (
            layer
            for layer in QgsProject.instance().mapLayers().values()
            if layer != exclude
        ),
        key=lambda layer: layer.name(),
    )


def layer_names(exclude=None):
    """プロジェクトのレイヤー名を、指定したレイヤーを除いて並べる。"""
    return [layer.name() for layer in loaded_layers(exclude)]


@pytest.fixture
def ksj_messages(qgis_app):
    """KSJタグで記録されたメッセージログを集める。"""
    messages = []

    def record(message, tag, level, message_format=None):
        if tag == "KSJ":
            messages.append(message)

    received = message_log_signal(qgis_app)
    received.connect(record)
    yield messages
    received.disconnect(record)


@pytest.fixture
def layer_choices(qgis_app):
    """実ダイアログに応答を順に返し、開いた一覧と未選択時の追加可否を記録する。"""
    responses, opened = [], []

    def answer():
        dialog = QApplication.activeModalWidget()
        if dialog is None or dialog.objectName() != "ksj-mesh-layers":
            return
        listing = dialog.findChild(QListWidget)
        button = dialog.findChild(QDialogButtonBox).button(
            QDialogButtonBox.StandardButton.Ok
        )
        opened.append(
            (
                [listing.item(i).text() for i in range(listing.count())],
                button.isEnabled(),
            )
        )
        response = responses.pop(0) if responses else None
        if callable(response):
            response = response()
        if response is None:
            dialog.reject()
            return
        for row in response:
            listing.item(row).setCheckState(Qt.CheckState.Checked)
        button.click()

    def choose(*answers):
        responses.extend(answers)
        return opened

    timer = QTimer()
    timer.timeout.connect(answer)
    timer.start(10)
    yield choose
    timer.stop()


def geojson_zip(archive, members):
    """{エントリ名: (properties, geometry)} を1地物ずつのGeoJSONとしてZIPに書く。"""
    with zipfile.ZipFile(archive, "w") as output:
        for name, (properties, geometry) in members.items():
            output.writestr(
                f"{name}.geojson",
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": properties,
                                "geometry": geometry,
                            }
                        ],
                    }
                ),
            )


MESH_RESOURCE = {
    "region": "5339",
    "year": "2024年",
    "filename": "data.zip",
    "url": "https://example.org/data.zip",
}


def local_resource(tmp_path, monkeypatch, filenames=("one", "two")):
    archive = tmp_path / "data.zip"
    geojson_zip(
        archive,
        {
            name: ({"name": name}, {"type": "Point", "coordinates": [139.5, 35.5]})
            for name in filenames
        },
    )
    # 取得のたびに読み直し、テスト中に書き換えた ZIP をそのまま配布する。
    monkeypatch.setattr(
        local_storage,
        "_download",
        lambda url, path, *args: path.write_bytes(archive.read_bytes()),
    )
    return dict(MESH_RESOURCE)


@pytest.mark.parametrize("entry_point", ["menu", "child"])
def test_year_action_adds_one_polygon_per_available_mesh(
    qgis_app, qgis_new_project, entry_point, mesh_action
):
    dataset = QgsDataCollectionItem(None, "道路", "/roads")
    item = mesh_year_item(dataset)
    if entry_point == "menu":
        actions = item.actions(None)
        assert actions, "メッシュ配布の年度には地図に索引を追加する操作が必要"
        actions[0].trigger()
    else:
        children = item.createChildren()
        assert children[0].name() == "メッシュ索引を地図に追加"
        assert children[0].handleDoubleClick() is True
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1
    layer = layers[0]
    assert "道路 2024年" in layer.name()
    assert layer.isValid() and layer.featureCount() == 2
    assert layer.labelsEnabled()
    tokyo = next(f for f in layer.getFeatures() if f["mesh_code"] == "5339")
    bounds = tokyo.geometry().boundingBox()
    assert (
        bounds.xMinimum(),
        bounds.yMinimum(),
        bounds.xMaximum(),
        bounds.yMaximum(),
    ) == pytest.approx((139, 35 + 1 / 3, 140, 36))
    assert len(json.loads(tokyo["resources"])) == 3
    assert not layer.actions().actions()
    assert QgsGui.mapLayerActionRegistry().defaultActionForLayer(layer) is mesh_action


def test_mesh_index_child_is_first_and_does_not_add_layer_on_expand(
    qgis_app, qgis_new_project
):
    item = mesh_year_item()
    children = item.createChildren()
    assert [child.name() for child in children] == [
        "メッシュ索引を地図に追加",
        "5339",
        "5439",
    ]
    assert [child.sortKey() for child in children] == [0, 1, 2]
    action = children[0]
    assert action.state() == QgsDataItem.State.Populated
    assert not action.icon().pixmap(24, 24).isNull()
    assert "ダブルクリック" in action.toolTip()
    assert len({child.path() for child in children}) == 3
    assert not QgsProject.instance().mapLayers()


def test_mesh_index_action_is_first_in_sorted_browser(qgis_app):
    # 表示用プロキシが項目の種類ではなくsortKeyで並べることは、単体のsortKey検証では示せない。
    item = mesh_year_item()

    class Provider(KsjDataItemProvider):
        def createDataItem(self, path, parent):
            return item if path == "" else None

    registry = qgis_app.dataItemProviderRegistry()
    provider = Provider()
    registry.addProvider(provider)
    model = QgsBrowserModel()
    proxy = QgsBrowserProxyModel()
    try:
        model.initialize()
        year = model.findPath("/roads/2024")
        model.fetchMore(year)
        pump_until(
            qgis_app, lambda: item.state() == QgsDataItem.State.Populated, timeout=10
        )
        proxy.setBrowserModel(model)
        proxy.sort(0)
        year = proxy.mapFromSource(year)
        assert [proxy.data(proxy.index(row, 0, year)) for row in range(3)] == [
            "メッシュ索引を地図に追加",
            "5339",
            "5439",
        ]
    finally:
        model.removeRootItems()
        registry.removeProvider(provider)
        qgis_app.processEvents()


@pytest.mark.parametrize(
    ("dimension", "region"), [("year", "東京都"), ("region", "5339")]
)
def test_mesh_index_child_is_absent_outside_mesh_years(qgis_app, dimension, region):
    item = catalog_browser.KsjResourceGroupItem(
        None,
        "項目",
        "/test",
        [{"region": region}],
        ("region",),
        dimension=dimension,
    )
    assert [child.name() for child in item.createChildren()] == [region]
    assert not item.actions(None)


@pytest.mark.parametrize("entry_point", ["default", "menu"])
@pytest.mark.parametrize("reopen", [False, True])
def test_index_action_loads_clicked_mesh_only(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, mesh_action, entry_point, reopen
):
    archives = {}
    for mesh, longitude in [("5339", 139.5), ("5439", 139.6)]:
        archive = tmp_path / f"{mesh}.zip"
        geojson_zip(
            archive,
            {
                "roads": (
                    {"mesh": mesh},
                    {
                        "type": "LineString",
                        "coordinates": [[longitude, 35.5], [longitude, 35.6]],
                    },
                )
            },
        )
        archives[mesh] = archive
    resources = [
        {
            "region": mesh,
            "year": "2024年",
            "filename": f"{mesh}.zip",
            "url": f"https://example.org/{mesh}.zip",
            "format": "GeoJSON",
        }
        for mesh in archives
    ]
    monkeypatch.setattr(
        local_storage,
        "_download",
        lambda url, path, *args: path.write_bytes(
            archives[url.rsplit("/", 1)[-1][:-4]].read_bytes()
        ),
    )
    layer = mesh_index.add_mesh_index("道路 2024年", resources)
    project = QgsProject.instance()
    layer_id = layer.id()
    if reopen:
        project_path = tmp_path / "mesh.qgz"
        assert project.write(str(project_path))
        project.clear()
        assert project.read(str(project_path))
    else:
        assert project.fileName() == ""
    restored = project.mapLayer(layer_id)
    assert restored.isValid() and restored.featureCount() == 2
    feature = next(f for f in restored.getFeatures() if f["mesh_code"] == "5339")
    assert not restored.actions().actions()
    action = QgsGui.mapLayerActionRegistry().defaultActionForLayer(restored)
    assert action is mesh_action
    if entry_point == "default":
        trigger = partial(
            action.triggerForFeature, restored, feature, QgsMapLayerActionContext()
        )
    else:
        menu = QgsActionMenu(restored, feature, "Feature")
        (entry,) = [
            a for a in menu.actions() if a.text() == mesh_index.MESH_ACTION_NAME
        ]
        trigger = entry.trigger
    trigger()
    wait_for_loads(qgis_app)
    assert len(project.mapLayers()) == 2
    loaded = next(
        layer for layer in project.mapLayers().values() if layer.id() != layer_id
    )
    assert loaded.featureCount() == 1
    assert next(loaded.getFeatures())["mesh"] == "5339"
    trigger()
    assert len(project.mapLayers()) == 2


def test_mesh_action_is_only_available_for_index_layers(
    qgis_app, qgis_new_project, mesh_action, tmp_path
):
    registry = QgsGui.mapLayerActionRegistry()
    index = mesh_index.add_mesh_index("道路", road_resources()[:1])
    vector = QgsVectorLayer("Point", "通常のレイヤー", "memory")
    raster = QgsRasterLayer(str(make_raster(tmp_path / "raster.tif")), "raster", "gdal")
    raster.setCustomProperty(mesh_index.INDEX_PROPERTY, True)
    for layer in [None, vector, raster]:
        assert mesh_action not in registry.mapLayerActions(layer)
    assert mesh_action in registry.mapLayerActions(index)


def test_action_unregisters_and_reenable_restores_existing_indexes(
    qgis_app, qgis_new_project
):
    registry = QgsGui.mapLayerActionRegistry()
    index = mesh_index.add_mesh_index("道路", road_resources()[:1])
    with registered_action() as action:
        assert registry.defaultActionForLayer(index) is action
    assert registry.defaultActionForLayer(index) is None
    assert action not in registry.mapLayerActions(index)
    second = mesh_index.add_mesh_index("道路", road_resources()[:1])
    assert registry.defaultActionForLayer(second) is None
    with registered_action() as replacement:
        assert registry.defaultActionForLayer(index) is replacement
        assert registry.defaultActionForLayer(second) is replacement


def test_removed_index_does_not_keep_default_action(
    qgis_app, qgis_new_project, mesh_action
):
    index = mesh_index.add_mesh_index("道路", road_resources()[:1])
    removed = QgsProject.instance().takeMapLayer(index)
    assert removed is index
    assert QgsGui.mapLayerActionRegistry().defaultActionForLayer(removed) is None


def test_removed_sublayer_can_be_loaded_again_without_duplicating_others(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, layer_choices
):
    layer_choices([0, 1], [0])
    resource = local_resource(tmp_path, monkeypatch)
    index = mesh_index.add_mesh_index("道路", [resource])
    feature_id = next(index.getFeatures()).id()
    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    project = QgsProject.instance()
    assert len(project.mapLayers()) == 3
    removed = next(
        layer for layer in project.mapLayers().values() if layer.name() == "one"
    )
    project.removeMapLayer(removed.id())
    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    assert layer_names() == ["one", "two", index.name()]


def test_mesh_adds_only_checked_layers_and_can_add_remaining_later(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, layer_choices
):
    resource = local_resource(tmp_path, monkeypatch, ("one", "two", "three"))
    opened = layer_choices([0, 2], [0])
    index = mesh_index.add_mesh_index("道路", [resource])
    feature_id = next(index.getFeatures()).id()

    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    assert layer_names(index) == ["one", "two"]
    assert len(opened) == 1
    texts, can_add = opened[0]
    assert len(texts) == 3
    assert can_add is False

    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    assert layer_names(index) == ["one", "three", "two"]
    assert len(opened) == 2
    texts, _ = opened[1]
    assert len(texts) == 1
    assert "three.geojson" in texts[0]

    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    assert len(opened) == 2
    assert len(QgsProject.instance().mapLayers()) == 4


def test_mesh_layer_selection_can_be_canceled_and_retried(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, layer_choices
):
    resource = local_resource(tmp_path, monkeypatch)
    opened = layer_choices(None, [1])
    index = mesh_index.add_mesh_index("道路", [resource])
    feature_id = next(index.getFeatures()).id()
    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    assert list(QgsProject.instance().mapLayers()) == [index.id()]
    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    assert len(opened) == 2
    assert layer_names() == ["two", index.name()]


def test_mesh_selection_distinguishes_shapefile_and_geojson_of_same_data(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, layer_choices
):
    resource = local_resource(tmp_path, monkeypatch, ("roads",))
    shapefile = tmp_path / "shape" / "roads.shp"
    shapefile.parent.mkdir()
    dataset = gdal.VectorTranslate(
        str(shapefile),
        f"/vsizip/{tmp_path}/data.zip/roads.geojson",
        format="ESRI Shapefile",
    )
    assert dataset is not None
    dataset = None
    with zipfile.ZipFile(tmp_path / "data.zip", "a") as archive:
        for path in shapefile.parent.iterdir():
            archive.write(path, path.name)
    opened = layer_choices([0])
    index = mesh_index.add_mesh_index("道路", [resource])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    data = [
        layer for layer in QgsProject.instance().mapLayers().values() if layer != index
    ]
    assert len(data) == 1
    assert "roads.geojson" in data[0].source()
    assert data[0].featureCount() == 1
    assert len(opened) == 1
    texts, _ = opened[0]
    assert "roads.geojson" in texts[0]
    assert "roads.shp" in texts[1]


@pytest.mark.parametrize("driver,suffix", [("GPKG", ".gpkg"), ("GML", ".gml")])
def test_mesh_selects_individual_sublayers_and_raster(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, layer_choices, driver, suffix
):
    resource = local_resource(tmp_path, monkeypatch, ())
    source = tmp_path / "source"
    source.mkdir()
    make_vector(source / ("multiple" + suffix), ["rivers", "stations"], driver=driver)
    make_raster(source / "elevation.tif")
    with zipfile.ZipFile(tmp_path / "data.zip", "a") as archive:
        for path in source.iterdir():
            archive.write(path, path.name)
    opened = layer_choices([0, 2])
    index = mesh_index.add_mesh_index("道路", [resource])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    data = {
        layer.name(): layer
        for layer in QgsProject.instance().mapLayers().values()
        if layer != index
    }
    assert set(data) == {"elevation.tif", "stations"}
    assert data["stations"].featureCount() == 1
    assert data["elevation.tif"].isValid()
    assert data["elevation.tif"].providerType() == "gdal"
    texts, _ = opened[0]
    assert len(texts) == 3


@pytest.mark.parametrize("remove_index", [False, True])
@pytest.mark.parametrize("mode", ["save", "temporary"])
def test_cancel_or_remove_index_during_selection_prevents_additions(
    qgis_app,
    qgis_new_project,
    tmp_path,
    monkeypatch,
    layer_choices,
    remove_index,
    storage_settings,
    temp_root,
    mode,
):
    QgsSettings().setValue(local_storage.MODE_KEY, mode)
    resource = local_resource(tmp_path, monkeypatch)
    index = mesh_index.add_mesh_index("道路", [resource])

    def cancel_while_open():
        if remove_index:
            QgsProject.instance().removeMapLayer(index.id())
        else:
            mesh_index.cancel_pending()
        return [0, 1]

    opened = layer_choices(cancel_while_open)
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    assert len(opened) == 1
    assert len(QgsProject.instance().mapLayers()) == (0 if remove_index else 1)
    assert not mesh_index._pending
    assert not workspaces(temp_root)


def test_cancel_and_reselect_does_not_let_old_callback_consume_new_task(
    qgis_app, qgis_new_project, tmp_path, monkeypatch
):
    resource = local_resource(tmp_path, monkeypatch, ("one",))
    index = mesh_index.add_mesh_index("道路", [resource])
    url = resource["url"]
    old = QgsTask.fromFunction("old", lambda task: None)
    new = QgsTask.fromFunction("new", lambda task: None)
    mesh_index._pending[url] = old
    mesh_index.cancel_pending()
    mesh_index._pending[url] = new
    mesh_index.finish_loading(old, index.id(), url, None)
    result = mesh_index.scan_resource(new, url, str(tmp_path))
    mesh_index.finish_loading(new, index.id(), url, None, result)
    assert len(QgsProject.instance().mapLayers()) == 2


@pytest.mark.parametrize("exceptions", [False, True])
def test_metadata_xml_is_skipped_but_broken_data_is_reported(
    qgis_app, tmp_path, monkeypatch, exceptions
):
    resource = local_resource(tmp_path, monkeypatch, ("one",))
    with zipfile.ZipFile(tmp_path / "data.zip", "a") as archive:
        archive.writestr("KS-META-test.xml", "<metadata/>")
        archive.writestr("broken.geojson", "broken")
    previous = gdal.GetUseExceptions()
    try:
        (gdal.UseExceptions if exceptions else gdal.DontUseExceptions)()
        result = mesh_index.scan_resource(
            QgsTask.fromFunction("scan", lambda task: None),
            resource["url"],
            str(tmp_path),
        )
        assert len(result["layers"]) == 1
        assert any("broken.geojson" in failure for failure in result["failed"])
        assert not any("KS-META" in failure for failure in result["failed"])
    finally:
        (gdal.UseExceptions if previous else gdal.DontUseExceptions)()


def test_invalid_loaded_layer_can_be_retried(
    qgis_app, qgis_new_project, tmp_path, monkeypatch
):
    resource = local_resource(tmp_path, monkeypatch, ("one",))
    index = mesh_index.add_mesh_index("道路", [resource])
    path = str(tmp_path / "missing.geojson")
    uri = (
        QgsProviderRegistry.instance()
        .providerMetadata("ogr")
        .encodeUri({"path": path, "layerName": "one"})
    )
    invalid = QgsVectorLayer(uri, "one", "ogr")
    assert not invalid.isValid()
    invalid.setCustomProperty(mesh_index.RESOURCE_PROPERTY, resource["url"])
    QgsProject.instance().addMapLayer(invalid)
    index.setCustomProperty(f"ksj/loaded/{resource['url']}", [uri])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    assert any(
        layer.isValid() and layer.name() == "one"
        for layer in QgsProject.instance().mapLayers().values()
    )


def test_retry_reports_broken_file_even_when_readable_layers_are_already_added(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, ksj_messages
):
    resource = local_resource(tmp_path, monkeypatch, ("one",))
    with zipfile.ZipFile(tmp_path / "data.zip", "a") as archive:
        archive.writestr("broken.geojson", "broken")
    index = mesh_index.add_mesh_index("道路", [resource])
    for _ in range(2):
        mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
        wait_for_loads(qgis_app)
        assert len(QgsProject.instance().mapLayers()) == 2
        assert "broken.geojson" in ksj_messages[-1]


@pytest.mark.parametrize("accept", [False, True])
def test_format_dialog_selects_exact_resource_or_cancels(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, accept
):
    resource = local_resource(tmp_path, monkeypatch, ("one",))
    alternative = {
        **resource,
        "filename": "alternative.zip",
        "url": "https://example.org/alternative.zip",
    }
    index = mesh_index.add_mesh_index("道路", [resource, alternative])
    dialogs = []

    def answer():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QInputDialog):
            dialogs.append(dialog.comboBoxItems())
            dialog.setTextValue(dialog.comboBoxItems()[1])
            (dialog.accept if accept else dialog.reject)()

    QTimer.singleShot(0, answer)
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    assert len(dialogs) == 1 and len(dialogs[0]) == 2
    data = [
        layer
        for layer in QgsProject.instance().mapLayers().values()
        if layer.id() != index.id()
    ]
    if accept:
        assert len(data) == 1
        assert (
            data[0].customProperty(mesh_index.RESOURCE_PROPERTY) == alternative["url"]
        )
    else:
        assert not data


def test_failure_is_reported_and_allows_retry(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, ksj_messages
):
    resource = local_resource(tmp_path, monkeypatch, ("one",))
    index = mesh_index.add_mesh_index("道路", [resource])
    scanner = mesh_index.scan_resource

    def fail(task, url, directory, temporary=None):
        raise RuntimeError("テスト用の接続失敗")

    monkeypatch.setattr(mesh_index, "scan_resource", fail)
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    assert len(QgsProject.instance().mapLayers()) == 1
    assert any("テスト用の接続失敗" in message for message in ksj_messages)
    monkeypatch.setattr(mesh_index, "scan_resource", scanner)
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    assert len(QgsProject.instance().mapLayers()) == 2


@pytest.mark.parametrize("remove_index", [False, True])
@pytest.mark.parametrize("mode", ["save", "temporary"])
def test_cancel_or_remove_index_prevents_late_additions(
    qgis_app,
    qgis_new_project,
    tmp_path,
    monkeypatch,
    remove_index,
    storage_settings,
    temp_root,
    mode,
):
    QgsSettings().setValue(local_storage.MODE_KEY, mode)
    resource = local_resource(tmp_path, monkeypatch, ("one",))
    index = mesh_index.add_mesh_index("道路", [resource])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    task = mesh_index._pending[resource["url"]]
    if remove_index:
        QgsProject.instance().removeMapLayer(index.id())
    else:
        mesh_index.cancel_pending()
    task.waitForFinished(5000)
    qgis_app.processEvents()
    assert len(QgsProject.instance().mapLayers()) == (0 if remove_index else 1)
    assert not mesh_index._pending
    assert not workspaces(temp_root)


def test_mesh_applies_detected_shapefile_encoding(
    qgis_app, qgis_new_project, tmp_path, monkeypatch
):
    (tmp_path / "src").mkdir()
    source = make_shapefile(tmp_path / "src" / "city.shp", ["札幌市中央区"], "cp932")
    mock_download(monkeypatch, zip_bytes(shapefile_entries(source)))
    index = mesh_index.add_mesh_index("行政区域", [dict(MESH_RESOURCE)])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    (layer,) = [
        layer
        for layer in QgsProject.instance().mapLayers().values()
        if layer.id() != index.id()
    ]
    assert layer.dataProvider().encoding() in SHIFT_JIS_NAMES
    assert next(layer.getFeatures())["name"] == "札幌市中央区"


def counted_downloads(tmp_path, monkeypatch):
    """local_resource と同じ配布データで取得を差し替え直し、要求された URL を集める。"""
    return mock_download(monkeypatch, (tmp_path / "data.zip").read_bytes())


def test_temporary_mode_fetches_into_workspace_and_removes_it_when_layers_close(
    qgis_app,
    qgis_new_project,
    tmp_path,
    monkeypatch,
    storage_settings,
    temp_root,
    layer_choices,
):
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    resource = local_resource(tmp_path, monkeypatch)
    layer_choices([0, 1])
    index = mesh_index.add_mesh_index("道路", [resource])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    layers = loaded_layers(index)
    assert [layer.name() for layer in layers] == ["one", "two"]
    (workspace,) = workspaces(temp_root)
    for layer in layers:
        assert stored_in(layer, workspace)
        assert layer.isTemporary()
        assert layer.customProperty(mesh_index.RESOURCE_PROPERTY) == resource["url"]
    # 保存先には何も残さない。
    assert not list(tmp_path.glob("data-*"))
    project = QgsProject.instance()
    project.removeMapLayer(layers[0].id())
    qgis_app.processEvents()
    assert workspaces(temp_root) == [workspace]
    project.removeMapLayer(layers[1].id())
    qgis_app.processEvents()
    assert not workspaces(temp_root)


@pytest.mark.parametrize("zipped", [False, True])
def test_scan_resource_uses_qgis_path_separators(qgis_app, monkeypatch, zipped):
    folder = r"C:\Users\test\AppData\Local\Temp\ksj-layer-test"
    path = folder if zipped else folder + r"\image.tif"
    monkeypatch.setattr(mesh_index, "Path", PureWindowsPath)
    monkeypatch.setattr(local_storage, "obtain_local_data", lambda *args: path)
    monkeypatch.setattr(
        mesh_index.zip_scanner, "supported_entries", lambda path: ["image.tif"]
    )
    task = SimpleNamespace(isCanceled=lambda: False, setProgress=lambda value: None)
    result = mesh_index.scan_resource(
        task, "https://example.org/data." + ("zip" if zipped else "tif"), "unused"
    )
    assert result["layers"] == [
        (
            "gdal",
            "C:/Users/test/AppData/Local/Temp/ksj-layer-test/image.tif",
            "image.tif",
        )
    ]


def test_temporary_mode_reuses_saved_distribution_without_downloading(
    qgis_app,
    qgis_new_project,
    tmp_path,
    monkeypatch,
    storage_settings,
    temp_root,
    layer_choices,
):
    resource = local_resource(tmp_path, monkeypatch)
    downloads = counted_downloads(tmp_path, monkeypatch)
    layer_choices([0, 1], [0, 1])
    index = mesh_index.add_mesh_index("道路", [resource])
    feature_id = next(index.getFeatures()).id()
    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    project = QgsProject.instance()
    for layer in loaded_layers(index):
        project.removeMapLayer(layer.id())
    assert downloads == [resource["url"]]

    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    layers = loaded_layers(index)
    assert [layer.name() for layer in layers] == ["one", "two"]
    assert downloads == [resource["url"]]
    (saved_root,) = tmp_path.glob("data-*")
    for layer in layers:
        assert stored_in(layer, saved_root)
    for layer in layers:
        project.removeMapLayer(layer.id())
    qgis_app.processEvents()
    assert saved_root.is_dir()
    assert not workspaces(temp_root)


def test_temporary_mode_never_asks_for_directory(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, storage_settings, temp_root
):
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    monkeypatch.setattr(local_storage, "download_directory", lambda: "")
    monkeypatch.setattr(
        local_storage,
        "choose_download_directory",
        lambda *args: pytest.fail("一時レイヤーでは保存先を尋ねない"),
    )
    resource = local_resource(tmp_path, monkeypatch, ("one",))
    index = mesh_index.add_mesh_index("道路", [resource])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    (layer,) = loaded_layers(index)
    assert layer.featureCount() == 1
    (workspace,) = workspaces(temp_root)
    assert stored_in(layer, workspace)


def test_temporary_mode_offers_all_layers_again_and_cancel_removes_workspace(
    qgis_app,
    qgis_new_project,
    tmp_path,
    monkeypatch,
    storage_settings,
    temp_root,
    layer_choices,
):
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    resource = local_resource(tmp_path, monkeypatch)
    opened = layer_choices([0], None)
    index = mesh_index.add_mesh_index("道路", [resource])
    feature_id = next(index.getFeatures()).id()
    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    assert layer_names(index) == ["one"]
    # 一時レイヤーは追加済みを除外せず、2 回目も全レイヤーを候補に出す。
    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    assert len(opened) == 2 and len(opened[1][0]) == 2
    assert layer_names(index) == ["one"]
    # キャンセルした 2 回目の一時ディレクトリは残らない。
    assert len(workspaces(temp_root)) == 1


def test_temporary_mode_after_save_offers_already_loaded_layers(
    qgis_app,
    qgis_new_project,
    tmp_path,
    monkeypatch,
    storage_settings,
    temp_root,
    layer_choices,
):
    resource = local_resource(tmp_path, monkeypatch)
    downloads = counted_downloads(tmp_path, monkeypatch)
    opened = layer_choices([0, 1], [0, 1], [0, 1])
    index = mesh_index.add_mesh_index("道路", [resource])
    feature_id = next(index.getFeatures()).id()
    mesh_index.load_mesh(index.id(), feature_id)
    wait_for_loads(qgis_app)
    recorded = index.customProperty(f"ksj/loaded/{resource['url']}")
    assert len(loaded_layers(index)) == 2
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    for count in (4, 6):
        mesh_index.load_mesh(index.id(), feature_id)
        wait_for_loads(qgis_app)
        assert len(loaded_layers(index)) == count
        assert index.customProperty(f"ksj/loaded/{resource['url']}") == recorded
    assert [len(options) for options, _ in opened] == [2, 2, 2]
    assert downloads == [resource["url"]]


@pytest.fixture
def pending_temporary_result(qgis_new_project, temp_root):
    """索引・待機中のタスク・一時ディレクトリ上の取得結果を用意し、後始末まで行う。"""
    index = mesh_index.add_mesh_index("道路", [dict(MESH_RESOURCE)])
    url = MESH_RESOURCE["url"]
    task = QgsTask.fromFunction("取得", lambda task: None)
    mesh_index._pending[url] = task
    workspace = temporary_files.workspace()
    path = point_file(Path(workspace.name), "point.geojson")
    yield index, task, workspace, path
    mesh_index._pending.pop(url, None)
    QgsProject.instance().removeAllMapLayers()
    temporary_files.cleanup(workspace)


@pytest.mark.parametrize(
    "outcome", ["cancel", "removed", "stale", "error", "empty", "invalid"]
)
def test_temporary_mode_discards_unused_workspace(
    qgis_app, pending_temporary_result, temp_root, outcome
):
    index, task, workspace, path = pending_temporary_result
    layer_id, url = index.id(), MESH_RESOURCE["url"]
    result = {"layers": [("ogr", str(path), "point")], "failed": []}
    exception = None
    if outcome == "cancel":
        task.cancel()
    elif outcome == "removed":
        QgsProject.instance().removeMapLayer(layer_id)
    elif outcome == "stale":
        replacement = QgsTask.fromFunction("再試行", lambda task: None)
        mesh_index._pending[url] = replacement
    elif outcome == "error":
        exception = RuntimeError("テスト用の取得失敗")
    elif outcome == "empty":
        result = None
    elif outcome == "invalid":
        path.unlink()
    mesh_index.finish_loading(
        task, layer_id, url, exception, result, mode="temporary", workspace=workspace
    )
    assert not workspaces(temp_root)
    assert len(QgsProject.instance().mapLayers()) == (0 if outcome == "removed" else 1)
    if outcome == "stale":
        assert mesh_index._pending[url] is replacement
    else:
        assert url not in mesh_index._pending


def test_temporary_mode_keeps_sources_if_notification_fails_after_addition(
    qgis_app, pending_temporary_result, monkeypatch, temp_root
):
    index, task, workspace, path = pending_temporary_result
    url = MESH_RESOURCE["url"]
    result = {"layers": [("ogr", str(path), "point")], "failed": []}

    def fail(*args, **kwargs):
        raise RuntimeError("テスト用の通知失敗")

    monkeypatch.setattr(mesh_index, "notify", fail)
    with pytest.raises(RuntimeError, match="通知失敗"):
        mesh_index.finish_loading(
            task, index.id(), url, None, result, mode="temporary", workspace=workspace
        )
    (layer,) = loaded_layers(index)
    assert path.is_file()
    assert layer.featureCount() == 1
    assert url not in mesh_index._pending
    QgsProject.instance().removeMapLayer(layer.id())
    qgis_app.processEvents()
    assert not workspaces(temp_root)


def test_mesh_kumoy_mode_hands_selected_layers_to_upload(
    qgis_app,
    qgis_new_project,
    tmp_path,
    monkeypatch,
    storage_settings,
    temp_root,
    layer_choices,
):
    QgsSettings().setValue(local_storage.MODE_KEY, "kumoy")
    monkeypatch.setattr(mesh_index.kumoy_upload, "ready", lambda parent=None: True)
    uploads = []

    def upload(layers, workspace, parent=None, is_current=None):
        assert all(Path(source.split("|")[0]).is_file() for _, source, _ in layers)
        uploads.append(sorted(name for _, _, name in layers))
        temporary_files.cleanup(workspace)

    monkeypatch.setattr(mesh_index.kumoy_upload, "upload_layers", upload)
    layer_choices([0, 1])
    resource = local_resource(tmp_path, monkeypatch)
    index = mesh_index.add_mesh_index("道路", [resource])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    assert uploads == [["one", "two"]]
    assert list(QgsProject.instance().mapLayers()) == [index.id()]
    assert not workspaces(temp_root)
    assert not list(tmp_path.glob("data-*"))


def test_mesh_kumoy_mode_stops_before_fetching_when_not_ready(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, storage_settings
):
    QgsSettings().setValue(local_storage.MODE_KEY, "kumoy")
    monkeypatch.setattr(mesh_index.kumoy_upload, "ready", lambda parent=None: False)
    monkeypatch.setattr(
        mesh_index,
        "scan_resource",
        lambda *args, **kwargs: pytest.fail("準備できていなければ取得しない"),
    )
    resource = local_resource(tmp_path, monkeypatch, ("one",))
    index = mesh_index.add_mesh_index("道路", [resource])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    assert not mesh_index._pending
