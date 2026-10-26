"""展開済みフォルダの走査モジュール

保存先に展開した通常フォルダ内のファイルを再帰的に列挙し、対応形式の階層を組み立てる。

公開 API:
    download_suffix(download_url: str) -> str
    list_entries_recursive(root: str) -> list[str]
    is_layer_file(path) -> bool
    is_archive(path) -> bool
    is_supported_entry(path) -> bool
    provider_key(path) -> str
    layer_source(path, separator=os.sep) -> str
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
# 配布データと分けて取得状態を保持する内部フォルダ。
STORAGE_METADATA = ".ksj"


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
        if Path(directory) == base and STORAGE_METADATA in folders:
            folders.remove(STORAGE_METADATA)
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


def is_archive(path) -> bool:
    """展開すればレイヤーを探せるZIPか"""
    return PurePosixPath(path).suffix.lower() == ".zip"


def is_supported_entry(path) -> bool:
    """ブラウザに並べる価値がある項目か（レイヤー形式、または入れ子ZIP）"""
    return is_layer_file(path) or is_archive(path)


def provider_key(path) -> str:
    """拡張子からQGISのプロバイダキー（ラスタは gdal、他は ogr）を返す"""
    return "gdal" if Path(path).suffix.lower() in RASTER_EXTENSIONS else "ogr"


def layer_source(path, separator=os.sep) -> str:
    """QGISのデータソースに使うパス文字列。OSの区切りを Qt と同じ '/' に揃える。

    QGISは一時レイヤーかどうかを、データソースのパスと Qt の一時フォルダ（'/' 区切り）
    の前方一致で判定する。Windows のドライブ・UNC パスも '/' にし、POSIX のファイル名に
    含まれる '\\' は保持する（Path.as_posix() と同じ変換）。
    separator は置き換える区切りで、他OSの区切りを試験で再現するために差し替えられる。
    """
    return str(Path(path)).replace(separator, "/")


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
    root = ZipNode(kind="folder", path="", name="", children=[])
    # フォルダはパスで引く。兄弟が多い配布でも一覧の長さに比例した時間で組み立てる。
    folders = {"": root}

    for file_path in paths:
        parts = file_path.split("/")
        parent = root
        current_path = ""
        for part in parts[:-1]:
            current_path = f"{current_path}/{part}" if current_path else part
            folder = folders.get(current_path)
            if folder is None:
                folder = ZipNode(
                    kind="folder", path=current_path, name=part, children=[]
                )
                folders[current_path] = folder
                parent.children.append(folder)
            parent = folder

        filename = parts[-1]
        _, ext = os.path.splitext(filename)
        parent.children.append(
            ZipNode(kind="file", path=file_path, name=filename, extension=ext)
        )

    return root
