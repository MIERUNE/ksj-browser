"""test_browser_items.py

ブラウザアイテム（ZIP内階層表示）のユニットテスト

テスト戦略:
- zip_scanner をモック化し、ZipNode ツリーを直接返す
- 都道府県ノード展開時の子要素生成をテスト
- ZIP内フォルダ/ファイルノードの正しい生成を検証
- エラーケース（走査失敗）も含める

注意: QGISモジュールが必要なテストは統合テストとして別途実施
"""

import json
import zipfile

from ksj.zip_scanner import ZipNode, ZipScanError

# 以下のテストはQGIS環境が必要なため、統合テストで実施
# ここではZipNodeからブラウザアイテムへの変換ロジックの検証に焦点を当てる


def test_zip_node_structure_flat():
    """単一階層のZipNodeツリー構造を検証"""
    # モック: 平坦なZIPツリー
    zip_tree = ZipNode(
        kind="folder",
        path="",
        name="",
        children=[
            ZipNode(
                kind="file",
                path="file1.shp",
                name="file1.shp",
                extension=".shp",
                is_supported=True,
            ),
            ZipNode(
                kind="file",
                path="file2.geojson",
                name="file2.geojson",
                extension=".geojson",
                is_supported=True,
            ),
            ZipNode(
                kind="file",
                path="readme.txt",
                name="readme.txt",
                extension=".txt",
                is_supported=False,
            ),
        ],
    )

    # 検証: 対象ファイル（is_supported=True）のみをカウント
    supported_files = [
        c for c in zip_tree.children if c.kind == "file" and c.is_supported
    ]
    assert len(supported_files) == 2


def test_zip_node_structure_nested():
    """ネストした階層のZipNodeツリー構造を検証"""
    # モック: 階層構造を持つZIPツリー
    zip_tree = ZipNode(
        kind="folder",
        path="",
        name="",
        children=[
            ZipNode(
                kind="file",
                path="root.shp",
                name="root.shp",
                extension=".shp",
                is_supported=True,
            ),
            ZipNode(
                kind="folder",
                path="data",
                name="data",
                children=[
                    ZipNode(
                        kind="file",
                        path="data/layer1.geojson",
                        name="layer1.geojson",
                        extension=".geojson",
                        is_supported=True,
                    ),
                    ZipNode(
                        kind="folder",
                        path="data/subdir",
                        name="subdir",
                        children=[
                            ZipNode(
                                kind="file",
                                path="data/subdir/layer2.shp",
                                name="layer2.shp",
                                extension=".shp",
                                is_supported=True,
                            )
                        ],
                    ),
                ],
            ),
        ],
    )

    # 検証: ルート直下に1ファイル + 1フォルダ
    assert len(zip_tree.children) == 2

    # data フォルダの検証
    data_folder = next(c for c in zip_tree.children if c.kind == "folder")
    assert data_folder.name == "data"
    assert len(data_folder.children) == 2  # 1ファイル + 1サブフォルダ


def test_zip_node_same_name_identification():
    """同名ファイル（異なるフォルダ）がpathで区別されることを検証"""
    # モック: 同名ファイルが異なるフォルダに存在
    zip_tree = ZipNode(
        kind="folder",
        path="",
        name="",
        children=[
            ZipNode(
                kind="folder",
                path="area1",
                name="area1",
                children=[
                    ZipNode(
                        kind="file",
                        path="area1/data.shp",
                        name="data.shp",
                        extension=".shp",
                        is_supported=True,
                    )
                ],
            ),
            ZipNode(
                kind="folder",
                path="area2",
                name="area2",
                children=[
                    ZipNode(
                        kind="file",
                        path="area2/data.shp",
                        name="data.shp",
                        extension=".shp",
                        is_supported=True,
                    )
                ],
            ),
        ],
    )

    # 検証: 各フォルダ内のdata.shpはpathで区別可能
    area1 = zip_tree.children[0]
    area2 = zip_tree.children[1]

    assert area1.children[0].name == "data.shp"
    assert area1.children[0].path == "area1/data.shp"

    assert area2.children[0].name == "data.shp"
    assert area2.children[0].path == "area2/data.shp"


def test_empty_zip_tree():
    """対象ファイルが無いZIPツリーの検証"""
    # モック: .shp / .geojson が無いZIPツリー
    zip_tree = ZipNode(
        kind="folder",
        path="",
        name="",
        children=[
            ZipNode(
                kind="file",
                path="readme.txt",
                name="readme.txt",
                extension=".txt",
                is_supported=False,
            )
        ],
    )

    # 検証: 対象ファイルが無いことを確認
    supported_files = [
        c for c in zip_tree.children if c.kind == "file" and c.is_supported
    ]
    assert len(supported_files) == 0


def test_zip_scan_error_structure():
    """ZipScanError が適切な情報を持つことを検証"""
    error = ZipScanError(
        user_message="ZIPファイルが見つかりません", debug_details="HTTP 404"
    )

    assert error.user_message == "ZIPファイルが見つかりません"
    assert error.debug_details == "HTTP 404"
    assert str(error) == "ZIPファイルが見つかりません"


def test_prefecture_node_creates_zip_items(qgis_app):
    from ksj.catalog_browser import KsjResourceGroupItem

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


def test_zip_folder_item_creates_children(qgis_app, tmp_path):
    from ksj.catalog_browser import archive_children
    from qgis.core import QgsDataCollectionItem, QgsVectorLayer

    inner = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("table.csv", "name,value\nsample,1\n")
    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as archive:
        archive.write(inner, "folder/inner.zip")
    parent = QgsDataCollectionItem(None, "test", "/test")
    folder = archive_children(parent, f"/vsizip/{outer}")[0]
    nested = folder.createChildren()[0]
    table = nested.createChildren()[0]
    uri = table.mimeUris()[0]
    layer = QgsVectorLayer(uri.uri, uri.name, uri.providerKey)
    assert layer.isValid()
    assert layer.featureCount() == 1


def test_zip_file_item_double_click(qgis_app, qgis_new_project, tmp_path):
    from ksj.browser import KsjZipFileItem
    from qgis.core import QgsProject

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
    item = KsjZipFileItem(None, "点", "/test/point", str(path))
    assert item.handleDoubleClick()
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1
    assert layers[0].name() == "点"
    assert layers[0].featureCount() == 1


def test_zip_file_item_drag_and_drop(qgis_app, qgis_new_project, tmp_path):
    from ksj.browser import KsjZipFileItem
    from osgeo import gdal
    from qgis.core import QgsRasterLayer

    path = tmp_path / "image.tif"
    dataset = gdal.GetDriverByName("GTiff").Create(str(path), 2, 2, 1)
    dataset.SetGeoTransform([140, 0.01, 0, 40, 0, -0.01])
    dataset.GetRasterBand(1).Fill(1)
    dataset = None
    item = KsjZipFileItem(None, "画像", "/test/image", str(path))
    assert item.hasDragEnabled()
    uri = item.mimeUris()[0]
    assert uri.layerType == "raster"
    assert uri.providerKey == "gdal"
    assert QgsRasterLayer(uri.uri, uri.name, uri.providerKey).isValid()
    assert item.handleDoubleClick()
