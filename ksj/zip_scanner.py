"""展開済みフォルダの走査モジュール

保存先に展開した通常フォルダ内のファイルを再帰的に列挙し、対応形式の階層を組み立てる。

公開 API:
    download_suffix(download_url: str) -> str
    list_entries_recursive(root: str) -> list[str]
    is_layer_file(path) -> bool
    provider_key(path) -> str
    filter_supported(paths: list[str]) -> list[str]
    supported_entries(root: str) -> list[str]
    build_tree(paths: list[str]) -> ZipNode

正規化ルール:
    - 返すパスは走査ルートからの相対パス（先頭 `/` なし）
    - 区切りは常に `/`（OS 依存の区切りは混入させない）
    - `.` / `..` を含めない
    - ファイルのみ返す（フォルダノードは build_tree() が生成する）

エラー:
    ZipScanError: 走査失敗を伝播する例外（user_message を持つ）
"""

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import List, Literal, Optional
from urllib.parse import urlsplit

RASTER_EXTENSIONS = {".tif", ".tiff", ".img", ".asc", ".vrt"}
# 1ファイルに複数レイヤーを持ちうる形式。サブレイヤーを列挙して個別に追加する。
MULTILAYER_EXTENSIONS = {".gml", ".xml", ".gpkg", ".kml"}
# 展開済みフォルダ内でレイヤーとして開ける形式。
LAYER_EXTENSIONS = (
    {".shp", ".geojson", ".csv"} | MULTILAYER_EXTENSIONS | RASTER_EXTENSIONS
)
# 取得して開ける配布形式。ZIPは展開してから LAYER_EXTENSIONS のファイルを探す。
SUPPORTED_EXTENSIONS = LAYER_EXTENSIONS | {".zip"}
# 国土数値情報の配布XMLメタデータ。空間レイヤーではないため走査から除く。
METADATA_PREFIX = "KS-META-"


class ZipScanError(Exception):
    """保存データの走査失敗を表す例外

    Args:
        user_message: ユーザー向けに表示可能なメッセージ
        debug_details: 診断用の詳細情報（オプション）
    """

    def __init__(self, user_message: str, debug_details: Optional[str] = None):
        self.user_message = user_message
        self.debug_details = debug_details
        super().__init__(user_message)


@dataclass
class ZipNode:
    """展開済みフォルダのフォルダ/ファイル階層を表現するノード

    Attributes:
        kind: ノード種別（'folder' | 'file'）
        path: 走査ルートからの相対パス（POSIX 形式、先頭 `/` なし）
        name: 表示名（パスの最終要素）
        extension: ファイル拡張子（file の場合のみ、例: '.shp'）
        children: 子ノード（folder の場合のみ）
    """

    kind: Literal["folder", "file"]
    path: str
    name: str
    extension: Optional[str] = None
    children: Optional[list["ZipNode"]] = None


def download_suffix(download_url: str) -> str:
    """配布URLのパス部分から小文字の拡張子を取り出す（クエリ文字列は無視）"""
    return PurePosixPath(urlsplit(download_url).path).suffix.lower()


def list_entries_recursive(root: str) -> List[str]:
    """フォルダ内のファイルパスを再帰的に列挙

    Args:
        root: 走査する展開済みフォルダ

    Returns:
        ファイルパス一覧（POSIX 形式、先頭 `/` なし、フォルダは含まない）

    Raises:
        ZipScanError: フォルダが無い・読めない時
    """
    base = Path(root)
    if not base.is_dir():
        raise ZipScanError(user_message=f"保存データのフォルダが見つかりません: {root}")

    def fail(error: OSError):
        raise ZipScanError(user_message=f"保存データの内容を取得できません: {error}")

    files = []
    # フォルダへのリンクは辿らないため、保存先の外を走査しない。
    for directory, folders, filenames in os.walk(base, onerror=fail):
        folders.sort()
        relative = Path(directory).relative_to(base)
        files.extend((relative / name).as_posix() for name in sorted(filenames))
    return files


def is_layer_file(path) -> bool:
    """レイヤーとして開ける形式か（配布メタデータXMLは除く）"""
    name = PurePosixPath(path).name
    suffix = PurePosixPath(name).suffix.lower()
    if suffix == ".xml" and name.upper().startswith(METADATA_PREFIX):
        return False
    return suffix in LAYER_EXTENSIONS


def provider_key(path) -> str:
    """拡張子からQGISのプロバイダキー（ラスタは gdal、他は ogr）を返す"""
    return "gdal" if Path(path).suffix.lower() in RASTER_EXTENSIONS else "ogr"


def filter_supported(paths: List[str]) -> List[str]:
    """レイヤーとして開ける形式のファイルだけを残す"""
    return [path for path in paths if is_layer_file(path)]


def supported_entries(root: str) -> List[str]:
    """展開済みフォルダ内でレイヤーとして開けるファイルの相対パス一覧"""
    return filter_supported(list_entries_recursive(root))


def build_tree(paths: List[str]) -> ZipNode:
    """ファイルパス一覧からフォルダ階層ツリーを生成

    Args:
        paths: 走査ルートからの相対ファイルパス一覧（POSIX 形式）

    Returns:
        ルート ZipNode（kind='folder', path='', children=[...]）
    """
    # ルートノード
    root = ZipNode(kind="folder", path="", name="", children=[])

    # パスごとにツリーに追加
    for file_path in paths:
        parts = file_path.split("/")
        current_node = root
        current_path = ""

        # フォルダ階層を辿る/作成する
        for part in parts[:-1]:
            if current_path:
                current_path = f"{current_path}/{part}"
            else:
                current_path = part

            # 既存のフォルダノードを探す
            folder_node = None
            for child in current_node.children:
                if child.kind == "folder" and child.name == part:
                    folder_node = child
                    break

            # なければ作成
            if folder_node is None:
                folder_node = ZipNode(
                    kind="folder", path=current_path, name=part, children=[]
                )
                current_node.children.append(folder_node)

            current_node = folder_node

        # ファイルノードを追加
        filename = parts[-1]
        _, ext = os.path.splitext(filename)

        file_node = ZipNode(kind="file", path=file_path, name=filename, extension=ext)
        current_node.children.append(file_node)

    return root
