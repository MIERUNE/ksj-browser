"""プラグインのアイコン。配布アイコンと、明暗どちらの背景でも読める線画アイコン。"""

from pathlib import Path, PurePosixPath

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon

from . import zip_scanner

ICON_DIR = Path(__file__).resolve().parent / "icons"


def browser_icon(role):
    return QIcon(str(ICON_DIR / f"{role}.svg"))


def plugin_icon():
    """プラグインを表すアイコン。ブラウザのルートと Processing プロバイダで共有する。"""
    return QIcon(str(ICON_DIR / "plugin.png"))


def file_icon(path):
    """内容を取得せず、ファイル形式を示す。ジオメトリ型は推測しない。"""
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in {".zip", ".lzh"}:
        return browser_icon("archive")
    if suffix in zip_scanner.RASTER_EXTENSIONS:
        return QgsApplication.getThemeIcon("/mIconRaster.svg")
    if suffix == ".csv":
        return QgsApplication.getThemeIcon("/mIconTableLayer.svg")
    # XMLには空間データ以外の文書も含まれる。読み込み可否は追加時に判定する。
    if suffix == ".xml" or not zip_scanner.is_layer_file(path):
        return browser_icon("document")
    return browser_icon("vector")
