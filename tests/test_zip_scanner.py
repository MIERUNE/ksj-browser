"""test_zip_scanner.py

ZIP 走査モジュール (ksj/zip_scanner.py) のユニットテスト。

テスト戦略:
- ネットワーク依存を避けるため、gdal.ReadDir を monkeypatch してモック化
- 小さなローカル ZIP を用意する代わりに、ReadDir の戻り値を直接制御
- 成功ケースとエラーケース（404/破損/空）を網羅
"""

import pytest

from ksj.zip_scanner import (
    ZipScanError,
    build_tree,
    filter_supported,
    list_entries,
    list_entries_recursive,
    vsi_zip_root,
)


def test_vsi_zip_root():
    """vsi_zip_root が正しい VSI パスを生成する"""
    url = "https://example.com/data.zip"
    expected = "/vsizip//vsicurl/https://example.com/data.zip"
    assert vsi_zip_root(url) == expected


def test_list_entries_success(monkeypatch):
    """list_entries が gdal.ReadDir の結果を正しく返す"""

    # モック: ReadDir が成功ケース
    def mock_readdir(path):
        if path == "/vsizip//vsicurl/https://example.com/data.zip":
            return ["file1.shp", "folder1/", "file2.geojson"]
        return None

    import ksj.zip_scanner

    monkeypatch.setattr(
        ksj.zip_scanner,
        "gdal",
        type("gdal", (), {"ReadDir": staticmethod(mock_readdir)})(),
    )

    root = vsi_zip_root("https://example.com/data.zip")
    entries = list_entries(root)

    assert "file1.shp" in entries
    assert "folder1/" in entries
    assert "file2.geojson" in entries


def test_list_entries_failure_raises_exception(monkeypatch):
    """list_entries が ReadDir 失敗時に ZipScanError を投げる"""

    def mock_readdir(path):
        return None  # 失敗シミュレーション

    import ksj.zip_scanner

    monkeypatch.setattr(
        ksj.zip_scanner,
        "gdal",
        type("gdal", (), {"ReadDir": staticmethod(mock_readdir)})(),
    )

    root = vsi_zip_root("https://example.com/missing.zip")

    with pytest.raises(ZipScanError) as exc_info:
        list_entries(root)

    assert (
        "取得できません" in exc_info.value.user_message
        or "失敗" in exc_info.value.user_message
    )


def test_list_entries_recursive(monkeypatch):
    """list_entries_recursive が再帰的にファイルのみを列挙する"""

    # モック: 階層構造を持つ ZIP
    def mock_readdir(path):
        if path == "/vsizip//vsicurl/https://example.com/data.zip":
            return ["file1.shp", "folder1"]
        elif path.endswith("folder1"):
            return ["file2.geojson", "subfolder"]
        elif "subfolder" in path:
            return ["file3.shp"]
        return None

    # VSIStatL モック: フォルダとファイルを区別
    class MockStat:
        def __init__(self, is_dir, size=0):
            self._is_dir = is_dir
            self.size = size

        def IsDirectory(self):
            return self._is_dir

    def mock_vsistatl(path):
        # フォルダ判定（folder1, subfolder）
        if path.endswith("/folder1") or path.endswith("/subfolder"):
            return MockStat(is_dir=True)
        # ファイル判定（.shp, .geojson など）
        return MockStat(is_dir=False, size=1000)

    import ksj.zip_scanner

    monkeypatch.setattr(
        ksj.zip_scanner,
        "gdal",
        type(
            "gdal",
            (),
            {
                "ReadDir": staticmethod(mock_readdir),
                "VSIStatL": staticmethod(mock_vsistatl),
            },
        )(),
    )

    root = vsi_zip_root("https://example.com/data.zip")
    files = list_entries_recursive(root)

    # ファイルのみ、フォルダ名は含まない
    assert "file1.shp" in files
    assert "folder1/file2.geojson" in files
    assert "folder1/subfolder/file3.shp" in files
    assert len(files) == 3


def test_filter_supported():
    """filter_supported が .shp と .geojson のみを抽出する"""
    paths = [
        "file1.shp",
        "file2.SHP",  # 大文字
        "file3.geojson",
        "file4.GeoJSON",  # 大文字
        "file5.txt",  # 対象外
        "file6.dbf",  # 対象外
        "folder1/file7.shp",
    ]

    supported = filter_supported(paths)

    assert "file1.shp" in supported
    assert "file2.SHP" in supported
    assert "file3.geojson" in supported
    assert "file4.GeoJSON" in supported
    assert "folder1/file7.shp" in supported
    assert "file5.txt" not in supported
    assert "file6.dbf" not in supported


def test_filter_supported_empty():
    """filter_supported が空リストを受け入れる"""
    assert filter_supported([]) == []


def test_build_tree_flat():
    """build_tree が単一階層のツリーを構築する"""
    paths = ["file1.shp", "file2.geojson"]

    root = build_tree(paths)

    assert root.kind == "folder"
    assert root.path == ""
    assert root.name == ""
    assert len(root.children) == 2

    # 子ノードがファイルノード
    child_names = {c.name for c in root.children}
    assert "file1.shp" in child_names
    assert "file2.geojson" in child_names


def test_build_tree_nested():
    """build_tree がネストした階層ツリーを構築する"""
    paths = [
        "file1.shp",
        "folder1/file2.geojson",
        "folder1/subfolder/file3.shp",
    ]

    root = build_tree(paths)

    assert root.kind == "folder"
    assert len(root.children) == 2  # file1.shp と folder1

    # folder1 を探す
    folder1 = next((c for c in root.children if c.name == "folder1"), None)
    assert folder1 is not None
    assert folder1.kind == "folder"
    assert folder1.path == "folder1"

    # folder1 の子
    assert len(folder1.children) == 2  # file2.geojson と subfolder

    subfolder = next((c for c in folder1.children if c.name == "subfolder"), None)
    assert subfolder is not None
    assert subfolder.kind == "folder"
    assert subfolder.path == "folder1/subfolder"

    # subfolder の子
    assert len(subfolder.children) == 1
    assert subfolder.children[0].name == "file3.shp"


def test_build_tree_same_name_files():
    """build_tree が同名ファイル（異なるフォルダ）を区別する"""
    paths = [
        "folder1/data.shp",
        "folder2/data.shp",
    ]

    root = build_tree(paths)

    # folder1, folder2 が区別されている
    folder_names = {c.name for c in root.children}
    assert "folder1" in folder_names
    assert "folder2" in folder_names

    # それぞれに data.shp が入っている
    folder1 = next(c for c in root.children if c.name == "folder1")
    folder2 = next(c for c in root.children if c.name == "folder2")

    assert folder1.children[0].name == "data.shp"
    assert folder1.children[0].path == "folder1/data.shp"

    assert folder2.children[0].name == "data.shp"
    assert folder2.children[0].path == "folder2/data.shp"


def test_zipnode_extension_and_is_supported():
    """ZipNode が拡張子と is_supported を正しく設定する"""
    paths = ["file1.shp", "file2.txt"]

    root = build_tree(paths)

    shp_node = next(c for c in root.children if c.name == "file1.shp")
    txt_node = next(c for c in root.children if c.name == "file2.txt")

    assert shp_node.extension == ".shp"
    assert shp_node.is_supported is True

    assert txt_node.extension == ".txt"
    assert txt_node.is_supported is False
    assert txt_node.is_supported is False
