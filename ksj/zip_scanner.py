"""リモート ZIP 走査モジュール

このモジュールは GDAL VSI (/vsizip//vsicurl) を用いてリモート ZIP 内のファイルを
再帰的に列挙し、対応するベクタ・ラスタ・入れ子ZIPを抽出する。

公開 API:
    download_suffix(download_url: str) -> str
    vsi_zip_root(download_url: str) -> str
    nested_zip_root(vsi_root: str, entry_path: str) -> str
    list_entries(vsi_zip_root: str) -> list[str]
    list_entries_recursive(vsi_zip_root: str) -> list[str]
    filter_supported(zip_paths: list[str]) -> list[str]
    build_tree(zip_paths: list[str]) -> ZipNode

正規化ルール:
    - 返すパスは ZIP ルートからの相対パス（先頭 `/` なし）
    - 区切りは常に `/`（OS 依存の区切りは混入させない）
    - `.` / `..` を含めない
    - ファイルのみ返す（フォルダノードは build_tree() が生成する）

エラー:
    ZipScanError: 取得失敗を伝播する例外（user_message を持つ）
"""

import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import List, Literal, Optional
from urllib.parse import urlsplit

RASTER_EXTENSIONS = {".tif", ".tiff", ".img", ".asc", ".vrt"}
# 1ファイルに複数レイヤーを持ちうる形式。サブレイヤーを列挙して個別に追加する。
MULTILAYER_EXTENSIONS = {".gml", ".xml", ".gpkg", ".kml"}
SUPPORTED_EXTENSIONS = (
    {".shp", ".geojson", ".csv", ".zip"} | MULTILAYER_EXTENSIONS | RASTER_EXTENSIONS
)

try:
    from osgeo import gdal
except ImportError:
    gdal = None  # テスト環境でのモック化対応

try:
    from qgis.core import Qgis, QgsMessageLog
except ImportError:
    QgsMessageLog = None  # テスト環境でのモック化対応
    Qgis = None


class ZipScanError(Exception):
    """ZIP 走査失敗を表す例外

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
    """ZIP 内のフォルダ/ファイル階層を表現するノード

    Attributes:
        kind: ノード種別（'folder' | 'file'）
        path: ZIP 内パス（POSIX 形式、先頭 `/` なし）
        name: 表示名（パスの最終要素）
        extension: ファイル拡張子（file の場合のみ、例: '.shp'）
        children: 子ノード（folder の場合のみ）
    """

    kind: Literal["folder", "file"]
    path: str
    name: str
    extension: Optional[str] = None
    children: Optional[list["ZipNode"]] = None


def vsi_zip_root(download_url: str) -> str:
    """ZIP のルート VSI パスを生成

    Args:
        download_url: リモート ZIP の URL

    Returns:
        `/vsizip//vsicurl/<download_url>` 形式のパス
    """
    return f"/vsizip//vsicurl/{download_url}"


def download_suffix(download_url: str) -> str:
    """配布URLのパス部分から小文字の拡張子を取り出す（クエリ文字列は無視）"""
    return PurePosixPath(urlsplit(download_url).path).suffix.lower()


def nested_zip_root(vsi_root: str, entry_path: str) -> str:
    """ZIP 内の ZIP を開く VSI パス。入れ子は波括弧で区切る"""
    return f"/vsizip/{{{vsi_root}/{entry_path}}}"


def list_entries(vsi_zip_root: str) -> List[str]:
    """ZIP 直下のエントリ名を列挙

    Args:
        vsi_zip_root: VSI ZIP ルートパス

    Returns:
        エントリ名一覧（フォルダ名/ファイル名）

    Raises:
        ZipScanError: 取得失敗時
    """
    if gdal is None:
        raise ZipScanError(
            user_message="GDAL が利用できません",
            debug_details="osgeo.gdal のインポートに失敗しました",
        )

    entries = gdal.ReadDir(vsi_zip_root)
    if entries is None:
        raise ZipScanError(
            user_message=f"ZIP の内容を取得できません: {vsi_zip_root}",
            debug_details="gdal.ReadDir() が None を返しました",
        )

    # デバッグ: 元のentriesをログ出力
    if QgsMessageLog is not None:
        QgsMessageLog.logMessage(
            f"list_entries [RAW]: {vsi_zip_root} -> {repr(entries)}",
            "KSJ ZIP Scanner",
            Qgis.Info,
        )

    # GDAL操作用に元のエンコーディングのまま返す
    return entries


def decode_entry_name(entry: str) -> str:
    """GDAL ReadDir()が返すエントリ名をShift-JISでデコード（表示用）

    Args:
        entry: GDAL ReadDir()が返したエントリ名（CP437として解釈された文字列）

    Returns:
        デコードされた表示用エントリ名
    """
    try:
        if isinstance(entry, bytes):
            # bytes型の場合は直接shift_jisでデコード
            return entry.decode("shift_jis")
        else:
            # 文字列の場合、まずASCII範囲内かチェック
            try:
                # CP437でバイト列に戻す
                encoded = entry.encode("cp437")
                # ASCII範囲内（0x00-0x7F）のみかチェック
                if all(b < 0x80 for b in encoded):
                    # ASCIIのみの場合はデコード不要
                    return entry
                else:
                    # 日本語などを含む場合はShift-JISでデコード
                    return encoded.decode("shift_jis")
            except (UnicodeDecodeError, UnicodeEncodeError):
                # CP437→Shift-JISで失敗した場合はlatin-1でも試す
                try:
                    return entry.encode("latin-1").decode("shift_jis")
                except (UnicodeDecodeError, UnicodeEncodeError):
                    # それでも失敗したら元の文字列を使用
                    return entry
    except (UnicodeDecodeError, AttributeError):
        # デコードに失敗した場合は元の文字列をそのまま使用
        return entry


def list_entries_recursive(vsi_zip_root: str) -> List[str]:
    """ZIP 内のファイルパスを再帰的に列挙

    Args:
        vsi_zip_root: VSI ZIP ルートパス

    Returns:
        ファイルパス一覧（POSIX 形式、先頭 `/` なし、フォルダは含まない）

    Raises:
        ZipScanError: 取得失敗時
    """
    if gdal is None:
        raise ZipScanError(
            user_message="GDAL が利用できません",
            debug_details="osgeo.gdal のインポートに失敗しました",
        )

    files = []

    def _scan_dir(current_path: str, prefix: str = ""):
        """再帰的にディレクトリを走査"""
        entries = list_entries(current_path)

        for entry in entries:
            # 正規化: POSIX区切りに統一
            entry_normalized = entry.replace("\\", "/").rstrip("/")

            if prefix:
                full_path = f"{prefix}/{entry_normalized}"
            else:
                full_path = entry_normalized

            # VSIStatL でフォルダかファイルかを判定
            entry_vsi_path = f"{current_path}/{entry_normalized}"
            stat = gdal.VSIStatL(entry_vsi_path)

            if stat and stat.IsDirectory():
                # フォルダの場合は再帰
                _scan_dir(entry_vsi_path, full_path)
            elif stat:
                # ファイルの場合はリストに追加
                files.append(full_path)

    _scan_dir(vsi_zip_root)
    return files


def filter_supported(zip_paths: List[str]) -> List[str]:
    """SUPPORTED_EXTENSIONSに含まれるファイルを抽出

    Args:
        zip_paths: ZIP 内ファイルパス一覧

    Returns:
        対象ファイルパス一覧
    """
    result = []

    for path in zip_paths:
        # 拡張子を小文字で取得
        _, ext = os.path.splitext(path)
        if ext.lower() in SUPPORTED_EXTENSIONS:
            result.append(path)

    return result


def build_tree(zip_paths: List[str]) -> ZipNode:
    """ファイルパス一覧からフォルダ階層ツリーを生成

    Args:
        zip_paths: ZIP 内ファイルパス一覧（POSIX 形式）

    Returns:
        ルート ZipNode（kind='folder', path='', children=[...]）
    """
    # ルートノード
    root = ZipNode(kind="folder", path="", name="", children=[])

    # パスごとにツリーに追加
    for file_path in zip_paths:
        parts = file_path.split("/")
        current_node = root
        current_path = ""

        # フォルダ階層を辿る/作成する
        for i, part in enumerate(parts[:-1]):
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
