"""実QGISのブラウザ項目で、分類と読み込み経路を確認する。"""

from ksj import catalog, zip_scanner


def test_dataset_loads_only_when_expanded(qgis_app, monkeypatch):
    from ksj.catalog_browser import KsjDatasetItem

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
    item = KsjDatasetItem(
        None,
        "/ksj/test",
        {
            "id": "test",
            "title": "テスト",
            "license": "条件",
            "resource_count": 1,
            "source_url": "https://example.org/info",
        },
    )
    assert calls == []
    years = item.createChildren()
    assert calls == ["test"]
    assert years[0].name() == "2025年（1ファイル）"
    regions = years[0].createChildren()
    assert regions[0].name() == "全国（1ファイル）"
    files = regions[0].createChildren()
    assert files[0].download_url == "https://example.org/all.zip"


def test_archive_preserves_gml_raster_csv_and_nested_zip(qgis_app, monkeypatch):
    from ksj.catalog_browser import KsjResourceItem

    monkeypatch.setattr(
        zip_scanner,
        "list_entries_recursive",
        lambda path: [
            "a.gml",
            "image.tif",
            "table.csv",
            "inner.zip",
            "a.dbf",
            "a.prj",
        ],
    )
    item = KsjResourceItem(
        None,
        "/ksj/test",
        {
            "url": "https://example.org/test.zip",
            "filename": "test.zip",
            "source_url": "https://example.org/info",
        },
    )
    files = item.createChildren()
    assert {f.name() for f in files} == {"a.gml", "image.tif", "table.csv", "inner.zip"}
    raster = next(f for f in files if f.name() == "image.tif")
    assert raster.mimeUris()[0].layerType == "raster"
    assert raster.mimeUris()[0].providerKey == "gdal"
    gml = next(f for f in files if f.name() == "a.gml")
    from ksj.browser import KsjVectorContainerItem

    assert isinstance(gml, KsjVectorContainerItem)
    inner = next(f for f in files if f.name() == "inner.zip")
    assert len(inner.createChildren()) == 4


def test_download_actions_available_when_archive_fails(qgis_app, monkeypatch):
    from ksj.catalog_browser import KsjResourceItem

    def fail(path):
        raise zip_scanner.ZipScanError("取得失敗")

    monkeypatch.setattr(zip_scanner, "list_entries_recursive", fail)
    item = KsjResourceItem(
        None,
        "/ksj/test",
        {
            "url": "https://example.org/test.zip",
            "filename": "test.zip",
            "source_url": "https://example.org/info",
        },
    )
    assert "取得失敗" in item.createChildren()[0].name()
    assert len(item.actions(None)) >= 2


def test_geopackage_exposes_every_layer(qgis_app, qgis_new_project, tmp_path):
    from osgeo import ogr
    from qgis.core import QgsProject
    from ksj.browser import KsjVectorContainerItem

    path = tmp_path / "multiple.gpkg"
    dataset = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    dataset.CreateLayer("rivers", geom_type=ogr.wkbLineString)
    dataset.CreateLayer("stations", geom_type=ogr.wkbPoint)
    dataset = None
    item = KsjVectorContainerItem(None, "multiple.gpkg", "/test/multiple", str(path))
    children = item.createChildren()
    assert {child.name() for child in children} == {"rivers", "stations"}
    assert len({child.mimeUris()[0].uri for child in children}) == 2
    assert {uri.name for uri in item.mimeUris()} == {"rivers", "stations"}
    assert item.handleDoubleClick()
    assert {layer.name() for layer in QgsProject.instance().mapLayers().values()} == {
        "rivers",
        "stations",
    }


def test_standard_gml_preserves_multiple_layers(qgis_app, qgis_new_project, tmp_path):
    from osgeo import ogr
    from qgis.core import QgsProject
    from ksj.browser import KsjVectorContainerItem

    path = tmp_path / "multiple.gml"
    dataset = ogr.GetDriverByName("GML").CreateDataSource(str(path))
    for name in ("rivers", "stations"):
        layer = dataset.CreateLayer(name, geom_type=ogr.wkbPoint)
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(ogr.CreateGeometryFromWkt("POINT (140 40)"))
        assert layer.CreateFeature(feature) == 0
        feature = None
    dataset = None
    item = KsjVectorContainerItem(None, "multiple.gml", "/test/gml", str(path))
    assert {child.name() for child in item.createChildren()} == {"rivers", "stations"}
    assert item.handleDoubleClick()
    assert len(QgsProject.instance().mapLayers()) == 2


def test_municipal_files_are_grouped_before_format_variants(qgis_app):
    from ksj.catalog_browser import KsjResourceGroupItem

    resources = [
        {
            "municipality": city,
            "filename": f"{city}_{fmt}.zip",
            "url": f"https://example.org/{city}_{fmt}.zip",
        }
        for city in ("札幌市", "函館市")
        for fmt in ("SHP", "GML")
    ]
    item = KsjResourceGroupItem(None, "北海道", "/test", resources)
    children = item.createChildren()
    assert [child.name() for child in children] == [
        "札幌市（2ファイル）",
        "函館市（2ファイル）",
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


def test_year_sort_keys_keep_latest_first(qgis_app, monkeypatch):
    from ksj.catalog_browser import KsjDatasetItem

    monkeypatch.setattr(
        catalog,
        "load_dataset",
        lambda dataset_id: {
            "resources": [
                {"year": "2023年", "region": "全国"},
                {"year": "2025年", "region": "全国"},
            ]
        },
    )
    item = KsjDatasetItem(
        None,
        "/test",
        {
            "id": "test",
            "title": "テスト",
            "resource_count": 2,
            "source_url": "https://example.org",
        },
    )
    children = item.createChildren()
    assert children[0].name().startswith("2025年")
    assert [child.sortKey() for child in children] == [0, 1]


def test_partial_dataset_shows_each_failed_page_beside_available_years(
    qgis_app, monkeypatch
):
    from ksj.catalog_browser import KsjDatasetItem, KsjWebItem

    issues = {
        "https://example.org/2020": "画像認証",
        "https://example.org/2021": "HTTPエラー",
    }
    monkeypatch.setattr(
        catalog,
        "load_dataset",
        lambda dataset_id: {
            "resources": [{"year": "2025年", "region": "全国"}],
            "issues": issues,
        },
    )
    item = KsjDatasetItem(
        None,
        "/test",
        {
            "id": "test",
            "title": "テスト",
            "resource_count": 1,
            "source_url": "https://example.org",
            "issues": issues,
        },
    )
    children = item.createChildren()
    warnings = [child for child in children if isinstance(child, KsjWebItem)]
    assert {child.url for child in warnings} == set(issues)
    assert len({child.path() for child in children}) == 3
    assert all("取得未完了" in child.name() for child in warnings)
    assert "未取得ページ: 2" in item.toolTip()
    assert any(child.name().startswith("2025年") for child in children)


def test_real_browser_model_populates_catalog_offline(qgis_app):
    import time
    from qgis.core import QgsApplication, QgsBrowserModel
    from ksj.browser import KsjDataItemProvider

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
    from ksj.catalog_browser import KsjCategoryItem

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
    from ksj.catalog_browser import KsjCategoryItem

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
    item = KsjCategoryItem(None, "旧統一フォーマット（TXT・CSV）", "/test", datasets)
    children = item.createChildren()
    assert [child.sortKey() for child in children] == [0, 1, 2]
    assert [child.name().split("（")[0] for child in children] == [
        "水域",
        "土地利用",
        "各種統計",
    ]


def test_unexpected_archive_error_is_shown_instead_of_propagating(
    qgis_app, monkeypatch
):
    from ksj.catalog_browser import KsjResourceItem

    def fail(path):
        raise RuntimeError("GDALの内部エラー")

    monkeypatch.setattr(zip_scanner, "list_entries_recursive", fail)
    item = KsjResourceItem(
        None,
        "/ksj/test",
        {
            "url": "https://example.org/test.zip",
            "filename": "test.zip",
            "source_url": "https://example.org/info",
        },
    )
    children = item.createChildren()
    assert "GDALの内部エラー" in children[0].name()
    assert len(item.actions(None)) >= 2
