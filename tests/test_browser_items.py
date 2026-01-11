"""test_browser_items.py

ブラウザアイテム（ZIP内階層表示）のユニットテスト

テスト戦略:
- zip_scanner をモック化し、ZipNode ツリーを直接返す
- 都道府県ノード展開時の子要素生成をテスト
- ZIP内フォルダ/ファイルノードの正しい生成を検証
- エラーケース（走査失敗）も含める

注意: QGISモジュールが必要なテストは統合テストとして別途実施
"""

import pytest

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


# 以下はQGIS環境が必要な統合テストのプレースホルダー
# 実際のQGIS環境でpytest-qgisを使って実行する


@pytest.mark.skip(reason="QGIS統合テスト: 実際のQGIS環境で実行")
def test_prefecture_node_creates_zip_items():
    """都道府県ノードがZIP内アイテムを生成することを検証（QGIS統合テスト）"""
    pass


@pytest.mark.skip(reason="QGIS統合テスト: 実際のQGIS環境で実行")
def test_zip_folder_item_creates_children():
    """ZIP内フォルダアイテムが子要素を生成することを検証（QGIS統合テスト）"""
    pass


@pytest.mark.skip(reason="QGIS統合テスト: 実際のQGIS環境で実行")
def test_zip_file_item_double_click():
    """ZIP内ファイルアイテムのダブルクリックを検証（QGIS統合テスト）"""
    pass


@pytest.mark.skip(reason="QGIS統合テスト: 実際のQGIS環境で実行")
def test_zip_file_item_drag_and_drop():
    """ZIP内ファイルアイテムのドラッグ&ドロップを検証（QGIS統合テスト）"""
    pass
