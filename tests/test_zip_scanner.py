"""test_zip_scanner.py

展開済みフォルダ走査モジュール (ksj/zip_scanner.py) のユニットテスト。

テスト戦略:
- tmp_path に実際のフォルダ構成を作り、列挙結果を直接検証
- 成功ケースとエラーケース（フォルダ無し）を網羅
"""

import pytest

from ksj.zip_scanner import (
    ZipScanError,
    build_tree,
    filter_supported,
    list_entries_recursive,
    supported_entries,
)


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def test_list_entries_recursive(tmp_path):
    """list_entries_recursive がルート相対のPOSIXパスでファイルのみを列挙する"""
    touch(tmp_path / "file1.shp")
    touch(tmp_path / "folder1" / "file2.geojson")
    touch(tmp_path / "folder1" / "subfolder" / "file3.shp")

    assert list_entries_recursive(str(tmp_path)) == [
        "file1.shp",
        "folder1/file2.geojson",
        "folder1/subfolder/file3.shp",
    ]


def test_missing_root_raises_exception(tmp_path):
    """list_entries_recursive がフォルダ無しの時に ZipScanError を投げる"""
    with pytest.raises(ZipScanError) as exc_info:
        list_entries_recursive(str(tmp_path / "missing"))

    assert "見つかりません" in exc_info.value.user_message


def test_local_directory_scan_stays_inside_root(tmp_path):
    """フォルダへのリンクを辿らず、保存先の外を走査しない"""
    root = tmp_path / "data"
    touch(root / "日本語" / "table.csv")
    outside = tmp_path / "outside"
    touch(outside / "other.csv")
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("この環境ではシンボリックリンクを作成できない")

    assert list_entries_recursive(str(root)) == ["日本語/table.csv"]


def test_supported_entries_skips_unsupported_files(tmp_path):
    """supported_entries が走査と形式判定をまとめて行う"""
    touch(tmp_path / "roads.shp")
    touch(tmp_path / "roads.dbf")
    touch(tmp_path / "inner.zip")

    assert supported_entries(str(tmp_path)) == ["roads.shp"]


def test_filter_supported():
    """filter_supported が .shp / .geojson / .gml のみを抽出する"""
    paths = [
        "file1.shp",
        "file2.SHP",  # 大文字
        "file3.geojson",
        "file4.GeoJSON",  # 大文字
        "file5.gml",  # GML（新規追加）
        "file6.GML",  # 大文字GML（新規追加）
        "file7.txt",  # 対象外
        "file8.dbf",  # 対象外
        "file11.zip",  # 展開済みフォルダには残らない。レイヤーとして開けない
        "folder1/file9.shp",
        "folder2/file10.gml",  # フォルダ内のGML
    ]

    supported = filter_supported(paths)

    assert "file1.shp" in supported
    assert "file2.SHP" in supported
    assert "file3.geojson" in supported
    assert "file4.GeoJSON" in supported
    assert "file5.gml" in supported
    assert "file6.GML" in supported
    assert "file7.txt" not in supported
    assert "file8.dbf" not in supported
    assert "file11.zip" not in supported
    assert "folder1/file9.shp" in supported
    assert "folder2/file10.gml" in supported


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


def test_zipnode_extension():
    """ZipNode が拡張子を正しく設定する"""
    paths = ["file1.shp", "file2.txt"]

    root = build_tree(paths)

    shp_node = next(c for c in root.children if c.name == "file1.shp")
    txt_node = next(c for c in root.children if c.name == "file2.txt")

    assert shp_node.extension == ".shp"
    assert txt_node.extension == ".txt"
