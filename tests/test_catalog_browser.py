"""実QGISのブラウザ項目で、分類と読み込み経路を確認する。"""

import json
import time

import pytest
from qgis.core import (
    QgsApplication,
    QgsBrowserModel,
    QgsDataCollectionItem,
    QgsDataItem,
)

from ksj import catalog, catalog_browser, local_storage, remote_zip, zip_scanner
from ksj.browser import KsjDataItemProvider, KsjRootItem
from ksj.catalog_browser import (
    KsjCategoryItem,
    KsjDatasetItem,
    KsjResourceGroupItem,
    KsjResourceItem,
    KsjWebItem,
    message_item,
)

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
        remote_zip,
        "list_members",
        lambda *args: [
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
    assert json.loads(raster.mimeUris()[0].uri)["member"] == "image.tif"
    gml = next(f for f in files if f.name() == "a.gml")
    assert isinstance(gml, catalog_browser.KsjFileItem)
    inner = next(f for f in files if f.name() == "inner.zip.files")
    assert [f.name() for f in inner.createChildren()] == ["table.csv"]


@pytest.mark.parametrize(
    "error",
    [zip_scanner.ZipScanError("取得失敗"), RuntimeError("GDALの内部エラー")],
    ids=["scan-error", "unexpected"],
)
def test_archive_failure_is_shown_with_download_actions(qgis_app, monkeypatch, error):
    """走査失敗も想定外例外も、伝播させずにエラーノードと取得手段を示す。"""

    def fail(*args):
        raise error

    monkeypatch.setattr(remote_zip, "list_members", fail)
    monkeypatch.setattr(local_storage, "download_directory", lambda: "/tmp")
    monkeypatch.setattr(local_storage, "ensure_local_data", lambda *args: "/tmp/data")
    item = resource_item()
    assert str(error) in item.createChildren()[0].name()
    assert item.createChildren()[0].type() == QgsDataItem.Error
    assert len(item.actions(None)) >= 2


def test_missing_catalogs_display_error_items(qgis_app, monkeypatch):
    def fail(*args):
        raise catalog.CatalogError("読み取り失敗")

    monkeypatch.setattr(catalog, "load_index", fail)
    monkeypatch.setattr(catalog, "load_dataset", fail)
    for item in (KsjRootItem(), KsjDatasetItem(None, "/test", DATASET)):
        child = next(
            child
            for child in item.createChildren()
            if child.type() == QgsDataItem.Error
        )
        assert child.type() == QgsDataItem.Error
        assert "読み取り失敗" in child.name()
        assert not child.icon().isNull()


def test_information_message_is_not_an_error(qgis_app):
    parent = QgsDataCollectionItem(None, "test", "/test")
    item = message_item(parent, "配布ファイルを確認してください")
    assert item.type() == QgsDataItem.Custom
    assert not item.icon().isNull()


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
