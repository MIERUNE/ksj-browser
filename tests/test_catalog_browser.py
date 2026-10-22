"""実QGISのブラウザ項目で、分類と読み込み経路を確認する。"""

import json
import time
from types import SimpleNamespace

import pytest
from osgeo import gdal, ogr
from qgis.core import (
    QgsApplication,
    QgsBrowserModel,
    QgsDataCollectionItem,
    QgsDataItem,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorLayer,
)

from ksj import catalog, catalog_browser, local_storage, zip_scanner
from ksj.browser import KsjDataItemProvider, KsjRootItem
from ksj.catalog_browser import (
    KsjCategoryItem,
    KsjDatasetItem,
    KsjResourceGroupItem,
    KsjResourceItem,
    KsjVectorContainerItem,
    KsjWebItem,
    KsjFileItem,
    directory_children,
    message_item,
)
from tests.helpers import mock_download, pump_until, zip_bytes

RESOURCE = {
    "url": "https://example.org/test.zip",
    "filename": "test.zip",
    "source_url": "https://example.org/info",
}
DATASET = {
    "id": "test",
    "title": "テスト",
    "resource_count": 1,
    "source_url": "https://example.org/info",
}


def resource_item(**overrides):
    return KsjResourceItem(None, "/ksj/test", {**RESOURCE, **overrides})


def dataset_item(monkeypatch, resources, issues=None, **overrides):
    """索引項目と読み込み結果の両方に、実カタログと同じく issues を持たせる。"""
    issues = issues or {}
    data = {"resources": resources, "issues": issues}
    monkeypatch.setattr(catalog, "load_dataset", lambda dataset_id: data)
    return KsjDatasetItem(None, "/ksj/test", {**DATASET, "issues": issues, **overrides})


def test_dataset_loads_only_when_expanded(qgis_app, monkeypatch):
    calls = []

    def load(dataset_id):
        calls.append(dataset_id)
        return {
            "resources": [
                {
                    "year": "2025年",
                    "region": "全国",
                    "filename": "all.zip",
                    "url": "https://example.org/all.zip",
                    "source_url": "https://example.org/info",
                }
            ]
        }

    monkeypatch.setattr(catalog, "load_dataset", load)
    item = KsjDatasetItem(None, "/ksj/test", {**DATASET, "license": "条件"})
    assert calls == []
    years = item.createChildren()
    assert calls == ["test"]
    assert years[0].name() == "2025年"
    assert "配布ファイル: 1件" in years[0].toolTip()
    regions = years[0].createChildren()
    assert regions[0].name() == "全国"
    assert "配布ファイル: 1件" in regions[0].toolTip()
    files = regions[0].createChildren()
    assert files[0].download_url == "https://example.org/all.zip"


def test_archive_preserves_gml_raster_csv_and_nested_zip(qgis_app, monkeypatch):
    monkeypatch.setattr(
        zip_scanner,
        "list_entries_recursive",
        lambda path: [
            "a.gml",
            "image.tif",
            "table.csv",
            "inner.zip.files/table.csv",
            "a.dbf",
            "a.prj",
        ],
    )
    monkeypatch.setattr(local_storage, "download_directory", lambda: "/tmp")
    monkeypatch.setattr(local_storage, "ensure_local_data", lambda *args: "/tmp/data")
    files = resource_item().createChildren()
    assert {f.name() for f in files} == {
        "a.gml",
        "image.tif",
        "table.csv",
        "inner.zip.files",
    }
    raster = next(f for f in files if f.name() == "image.tif")
    assert raster.mimeUris()[0].layerType == "raster"
    assert raster.mimeUris()[0].providerKey == "gdal"
    gml = next(f for f in files if f.name() == "a.gml")
    assert isinstance(gml, KsjVectorContainerItem)
    inner = next(f for f in files if f.name() == "inner.zip.files")
    assert [f.name() for f in inner.createChildren()] == ["table.csv"]


@pytest.mark.parametrize(
    "error",
    [zip_scanner.ZipScanError("取得失敗"), RuntimeError("GDALの内部エラー")],
    ids=["scan-error", "unexpected"],
)
def test_archive_failure_is_shown_with_download_actions(qgis_app, monkeypatch, error):
    """走査失敗も想定外例外も、伝播させずにエラーノードと取得手段を示す。"""

    def fail(path):
        raise error

    monkeypatch.setattr(zip_scanner, "list_entries_recursive", fail)
    monkeypatch.setattr(local_storage, "download_directory", lambda: "/tmp")
    monkeypatch.setattr(local_storage, "ensure_local_data", lambda *args: "/tmp/data")
    item = resource_item()
    assert str(error) in item.createChildren()[0].name()
    assert item.createChildren()[0].type() == QgsDataItem.Error
    assert len(item.actions(None)) >= 2


@pytest.mark.parametrize("failure", [None, RuntimeError("列挙失敗")])
def test_container_caches_empty_or_failed_query(qgis_app, monkeypatch, failure):
    calls = []

    def query(path):
        calls.append(path)
        if failure:
            raise failure
        return []

    provider = SimpleNamespace(querySublayers=query)
    registry = SimpleNamespace(providerMetadata=lambda key: provider)
    monkeypatch.setattr(
        catalog_browser,
        "QgsProviderRegistry",
        SimpleNamespace(instance=lambda: registry),
    )
    item = KsjVectorContainerItem(None, "test", "/test", "test.gml")
    children = item.createChildren()
    assert len(children) == 1
    assert item.mimeUris() == []
    assert not item.handleDoubleClick()
    assert calls == ["test.gml"]
    if failure:
        assert children[0].type() == QgsDataItem.Error
        assert str(failure) in children[0].name()
    else:
        assert children[0].type() == QgsDataItem.Custom


def test_missing_catalogs_display_error_items(qgis_app, monkeypatch):
    def fail(*args):
        raise catalog.CatalogError("読み取り失敗")

    monkeypatch.setattr(catalog, "load_index", fail)
    monkeypatch.setattr(catalog, "load_dataset", fail)
    for item in (KsjRootItem(), KsjDatasetItem(None, "/test", DATASET)):
        child = item.createChildren()[0]
        assert child.type() == QgsDataItem.Error
        assert "読み取り失敗" in child.name()
        assert not child.icon().isNull()


def test_information_message_is_not_an_error(qgis_app):
    parent = QgsDataCollectionItem(None, "test", "/test")
    item = message_item(parent, "配布ファイルを確認してください")
    assert item.type() == QgsDataItem.Custom
    assert not item.icon().isNull()


def test_resource_reload_retries_failed_sublayer_query(qgis_app, tmp_path, monkeypatch):
    path = tmp_path / "test.gpkg"
    data = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    data.CreateLayer("rivers", geom_type=ogr.wkbPoint)
    data = None
    query = QgsProviderRegistry.instance().providerMetadata("ogr").querySublayers
    calls = []

    def flaky_query(source):
        calls.append(source)
        if len(calls) == 1:
            raise RuntimeError("一時的な列挙失敗")
        return query(source)

    provider = SimpleNamespace(querySublayers=flaky_query)
    registry = SimpleNamespace(providerMetadata=lambda key: provider)
    monkeypatch.setattr(
        catalog_browser,
        "QgsProviderRegistry",
        SimpleNamespace(instance=lambda: registry),
    )
    monkeypatch.setattr(local_storage, "download_directory", lambda: str(tmp_path))
    monkeypatch.setattr(local_storage, "ensure_local_data", lambda *args: str(path))

    class Root(KsjRootItem):
        def createChildren(self):
            return [
                KsjResourceItem(
                    self,
                    "/ksj/test",
                    {"url": "https://example.org/test.gpkg", "filename": "test.gpkg"},
                )
            ]

    class Provider(KsjDataItemProvider):
        def createDataItem(self, path, parent):
            return Root() if path == "" else None

    item_registry = QgsApplication.dataItemProviderRegistry()
    item_provider = Provider()
    item_registry.addProvider(item_provider)
    model = QgsBrowserModel()

    def expand(index):
        model.fetchMore(index)
        pump_until(qgis_app, lambda: model.rowCount(index) > 0, timeout=5)
        return model.index(0, 0, index)

    try:
        model.initialize()
        resource = expand(model.findPath("/ksj"))
        container = expand(resource)
        error = expand(container)
        assert model.dataItem(error).type() == QgsDataItem.Error
        actions = model.dataItem(resource).actions(None)
        retry = next(action for action in actions if "再読み込み" in action.text())
        retry.trigger()
        pump_until(
            qgis_app,
            lambda: model.dataItem(resource).state() == QgsDataItem.Populated,
            timeout=5,
        )
        container = model.index(0, 0, resource)
        layer = expand(container)
        assert model.data(layer) == "rivers"
        assert calls == [str(path), str(path)]
    finally:
        model.removeRootItems()
        item_registry.removeProvider(item_provider)
        qgis_app.processEvents()


def test_root_tooltip_is_ready_before_expansion_and_not_mutated(qgis_app):
    item = KsjRootItem()
    assert "公式一覧" in item.toolTip()
    assert "カタログ取得" in item.toolTip()
    assert "保存先" in item.toolTip()
    # 子生成が別スレッドの親に書き込まないことを検証する。
    item.setToolTip("生成後に設定したツールチップ")
    assert item.createChildren()
    assert item.toolTip() == "生成後に設定したツールチップ"


@pytest.mark.parametrize(
    "field,value",
    [
        ("generated_at", None),
        ("dataset_count", "invalid"),
        ("resource_count", []),
        ("errors", 1),
    ],
)
def test_incomplete_summary_keeps_root_and_datasets_available(
    qgis_app, monkeypatch, field, value
):
    index = catalog.load_index()
    if value is None:
        del index[field]
    else:
        index[field] = value
    monkeypatch.setattr(catalog, "load_index", lambda: index)
    item = KsjRootItem()
    assert "読み込めません" in item.toolTip()
    assert item.createChildren()


@pytest.mark.parametrize("driver,suffix", [("GPKG", ".gpkg"), ("GML", ".gml")])
def test_container_exposes_every_layer(
    qgis_app, qgis_new_project, tmp_path, driver, suffix
):
    path = tmp_path / f"multiple{suffix}"
    dataset = ogr.GetDriverByName(driver).CreateDataSource(str(path))
    for name in ("rivers", "stations"):
        layer = dataset.CreateLayer(name, geom_type=ogr.wkbPoint)
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(ogr.CreateGeometryFromWkt("POINT (140 40)"))
        assert layer.CreateFeature(feature) == 0
        feature = None
    dataset = None
    item = KsjVectorContainerItem(None, path.name, "/test/multiple", str(path))
    children = item.createChildren()
    assert {child.name() for child in children} == {"rivers", "stations"}
    assert len({child.mimeUris()[0].uri for child in children}) == 2
    assert {uri.name for uri in item.mimeUris()} == {"rivers", "stations"}
    assert item.handleDoubleClick()
    assert {layer.name() for layer in QgsProject.instance().mapLayers().values()} == {
        "rivers",
        "stations",
    }


def test_resource_group_without_dimensions_lists_files(qgis_app):
    item = KsjResourceGroupItem(
        None,
        "北海道",
        "/test",
        [
            {"filename": "a.zip", "url": "https://example.org/a.zip"},
            {"filename": "b.zip", "url": "https://example.org/b.zip"},
        ],
    )
    assert len(item.createChildren()) == 2


def test_municipal_files_are_grouped_before_format_variants(qgis_app):
    resources = [
        {
            "municipality": city,
            "filename": f"{city}_{fmt}.zip",
            "url": f"https://example.org/{city}_{fmt}.zip",
        }
        for city in ("札幌市", "函館市")
        for fmt in ("SHP", "GML")
    ]
    item = KsjResourceGroupItem(None, "北海道", "/test", resources, ("municipality",))
    children = item.createChildren()
    assert [child.name() for child in children] == [
        "札幌市",
        "函館市",
    ]
    # sortKey未設定だとname()順（函館市が先）になるため、公式掲載順を明示する。
    assert [child.sortKey() for child in children] == [0, 1]
    files = children[0].createChildren()
    assert len(files) == 2
    assert [f.resource["filename"] for f in files] == [
        "札幌市_SHP.zip",
        "札幌市_GML.zip",
    ]
    assert [f.sortKey() for f in files] == [0, 1]


def test_municipality_level_is_skipped_when_no_file_has_one(qgis_app):
    resources = [{"url": "https://example.org/a.zip", "filename": "a.zip"}]
    item = KsjResourceGroupItem(None, "北海道", "/test", resources, ("municipality",))
    assert isinstance(item.createChildren()[0], KsjResourceItem)


def test_year_sort_keys_keep_latest_first(qgis_app, monkeypatch):
    item = dataset_item(
        monkeypatch,
        [
            {"year": "2023年", "region": "全国"},
            {"year": "2025年", "region": "全国"},
        ],
        resource_count=2,
    )
    children = item.createChildren()
    assert children[0].name().startswith("2025年")
    assert [child.sortKey() for child in children] == [0, 1]


def test_partial_dataset_shows_each_failed_page_beside_available_years(
    qgis_app, monkeypatch
):
    issues = {
        "https://example.org/2020": "画像認証",
        "https://example.org/2021": "HTTPエラー",
    }
    item = dataset_item(monkeypatch, [{"year": "2025年", "region": "全国"}], issues)
    children = item.createChildren()
    warnings = [child for child in children if isinstance(child, KsjWebItem)]
    assert {child.url for child in warnings} == set(issues)
    assert len({child.path() for child in children}) == 3
    assert all("取得未完了" in child.name() for child in warnings)
    assert "未取得ページ: 2" in item.toolTip()
    assert any(child.name().startswith("2025年") for child in children)


def test_real_browser_model_populates_catalog_offline(qgis_app):
    registry = QgsApplication.dataItemProviderRegistry()
    provider = KsjDataItemProvider()
    registry.addProvider(provider)
    model = QgsBrowserModel()
    try:
        model.initialize()
        root = model.findPath("/ksj")
        assert root.isValid()
        model.fetchMore(root)
        deadline = time.monotonic() + 10
        while not model.rowCount(root) and time.monotonic() < deadline:
            qgis_app.processEvents()
            time.sleep(0.01)
        assert model.rowCount(root) >= 4
        names = [
            model.data(model.index(row, 0, root)) for row in range(model.rowCount(root))
        ]
        assert any("災害・防災" in name for name in names)
        assert any("旧統一フォーマット" in name for name in names)
    finally:
        model.removeRootItems()
        registry.removeProvider(provider)
        qgis_app.processEvents()


def test_category_keeps_official_dataset_order(qgis_app):
    datasets = [
        {
            "id": f"ksj-{index}",
            "title": title,
            "edition": "現行形式",
            "category": "水域",
            "resource_count": 1,
            "source_url": f"https://example.org/{index}",
        }
        for index, title in enumerate(("海岸線", "湖沼", "ダム", "河川"))
    ]
    item = KsjCategoryItem(None, "水域", "/test", datasets)
    children = item.createChildren()
    # sortKey未設定だと表示名のコードポイント順になり、公式一覧の掲載順が崩れる。
    assert [child.sortKey() for child in children] == [0, 1, 2, 3]
    assert [child.name().split("（")[0] for child in children] == [
        "海岸線",
        "湖沼",
        "ダム",
        "河川",
    ]


def test_legacy_edition_subcategories_keep_official_order(qgis_app):
    datasets = [
        {
            "id": f"old-{index}",
            "title": f"旧データ{index}",
            "edition": "旧統一フォーマット（TXT・CSV）",
            "category": category,
            "resource_count": 1,
            "source_url": f"https://example.org/old-{index}",
        }
        for index, category in enumerate(("水域", "土地利用", "各種統計"))
    ]
    item = KsjCategoryItem(
        None, "旧統一フォーマット（TXT・CSV）", "/test", datasets, subdivide=True
    )
    children = item.createChildren()
    assert [child.sortKey() for child in children] == [0, 1, 2]
    assert [child.name().split("（")[0] for child in children] == [
        "水域",
        "土地利用",
        "各種統計",
    ]


def test_nested_archive_table_is_readable(qgis_app, tmp_path, monkeypatch):
    inner = zip_bytes([("table.csv", "name,value\nsample,1\n")])
    mock_download(monkeypatch, zip_bytes([("folder/inner.zip", inner)]))
    parent = QgsDataCollectionItem(None, "test", "/test")
    root = local_storage.ensure_local_data(RESOURCE["url"], str(tmp_path))
    folder = directory_children(parent, root)[0]
    nested = folder.createChildren()[0]
    table = nested.createChildren()[0]
    uri = table.mimeUris()[0]
    assert "/vsi" not in uri.uri
    layer = QgsVectorLayer(uri.uri, uri.name, uri.providerKey)
    assert layer.isValid()
    assert layer.featureCount() == 1


def test_vector_file_item_double_click_adds_layer(qgis_app, qgis_new_project, tmp_path):
    path = tmp_path / "point.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "test"},
                        "geometry": {"type": "Point", "coordinates": [140, 40]},
                    }
                ],
            }
        )
    )
    item = KsjFileItem(None, "点", "/test/point", str(path))
    assert item.handleDoubleClick()
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1
    assert layers[0].name() == "点"
    assert layers[0].featureCount() == 1


def test_raster_file_item_uses_gdal_provider(qgis_app, qgis_new_project, tmp_path):
    path = tmp_path / "image.tif"
    dataset = gdal.GetDriverByName("GTiff").Create(str(path), 2, 2, 1)
    dataset.SetGeoTransform([140, 0.01, 0, 40, 0, -0.01])
    dataset.GetRasterBand(1).Fill(1)
    dataset = None
    item = KsjFileItem(None, "画像", "/test/image", str(path))
    assert item.hasDragEnabled()
    uri = item.mimeUris()[0]
    assert uri.layerType == "raster"
    assert uri.providerKey == "gdal"
    assert QgsRasterLayer(uri.uri, uri.name, uri.providerKey).isValid()
    assert item.handleDoubleClick()
