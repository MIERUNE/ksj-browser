"""メッシュから配布データを探して追加する操作を実QGISで検証する。"""

import json
import zipfile

import pytest
from osgeo import gdal
from qgis import utils
from qgis.core import (
    QgsBrowserModel,
    QgsBrowserProxyModel,
    QgsDataCollectionItem,
    QgsDataItem,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsProject,
    QgsProviderRegistry,
    QgsTask,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication, QInputDialog

from ksj import catalog, catalog_browser, local_storage, mesh_index
from ksj.browser import KsjDataItemProvider
from tests.helpers import pump_until


@pytest.fixture(autouse=True)
def without_gui_interface(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "iface", None)
    monkeypatch.setattr(local_storage, "download_directory", lambda: str(tmp_path))


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


def local_resource(tmp_path, monkeypatch, filenames=("one", "two")):
    archive = tmp_path / "data.zip"
    geojson_zip(
        archive,
        {
            name: ({"name": name}, {"type": "Point", "coordinates": [139.5, 35.5]})
            for name in filenames
        },
    )
    monkeypatch.setattr(
        local_storage,
        "_download",
        lambda url, path, *args: path.write_bytes(archive.read_bytes()),
    )
    return {
        "region": "5339",
        "year": "2024年",
        "filename": "data.zip",
        "url": "https://example.org/data.zip",
    }


@pytest.mark.parametrize("entry_point", ["menu", "child"])
def test_year_action_adds_one_polygon_per_available_mesh(
    qgis_app, qgis_new_project, entry_point
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
    assert layer.actions().defaultAction("Canvas").isValid()


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
    assert action.state() == QgsDataItem.Populated
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
        pump_until(qgis_app, lambda: item.state() == QgsDataItem.Populated, timeout=10)
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


def test_saved_index_action_loads_clicked_mesh_only(
    qgis_app, qgis_new_project, tmp_path, monkeypatch
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
    project_path = tmp_path / "mesh.qgz"
    assert project.write(str(project_path))
    project.clear()
    assert project.read(str(project_path))
    restored = project.mapLayer(layer_id)
    assert restored.isValid() and restored.featureCount() == 2
    feature = next(f for f in restored.getFeatures() if f["mesh_code"] == "5339")
    context = QgsExpressionContext()
    context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(restored))
    context.setFeature(feature)
    action = restored.actions().defaultAction("Canvas")
    command = QgsExpression.replaceExpressionText(action.command(), context)
    # QGIS GUIのPython runnerと同じ、展開後のアクションを実行する。
    exec(command)
    wait_for_loads(qgis_app)
    assert len(project.mapLayers()) == 2
    loaded = next(
        layer for layer in project.mapLayers().values() if layer.id() != layer_id
    )
    assert loaded.featureCount() == 1
    assert next(loaded.getFeatures())["mesh"] == "5339"
    exec(command)
    assert len(project.mapLayers()) == 2


def test_removed_sublayer_can_be_loaded_again_without_duplicating_others(
    qgis_app, qgis_new_project, tmp_path, monkeypatch
):
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
    assert sorted(layer.name() for layer in project.mapLayers().values()) == [
        "one",
        "two",
        index.name(),
    ]


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
    qgis_app, qgis_new_project, tmp_path, monkeypatch
):
    resource = local_resource(tmp_path, monkeypatch, ("one",))
    index = mesh_index.add_mesh_index("道路", [resource])
    scanner = mesh_index.scan_resource
    messages = []

    def fail(task, url, directory):
        raise RuntimeError("テスト用の接続失敗")

    def record(message, tag, level):
        if tag == "KSJ":
            messages.append(message)

    qgis_app.messageLog().messageReceived.connect(record)
    try:
        monkeypatch.setattr(mesh_index, "scan_resource", fail)
        mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
        wait_for_loads(qgis_app)
        assert len(QgsProject.instance().mapLayers()) == 1
        assert any("テスト用の接続失敗" in message for message in messages)
        monkeypatch.setattr(mesh_index, "scan_resource", scanner)
        mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
        wait_for_loads(qgis_app)
        assert len(QgsProject.instance().mapLayers()) == 2
    finally:
        qgis_app.messageLog().messageReceived.disconnect(record)


@pytest.mark.parametrize("remove_index", [False, True])
def test_cancel_or_remove_index_prevents_late_additions(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, remove_index
):
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
