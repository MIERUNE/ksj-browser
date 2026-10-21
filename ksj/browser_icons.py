"""ブラウザの役割を示す、明暗どちらの背景でも読める線画アイコン。"""

from pathlib import Path

from qgis.PyQt.QtGui import QIcon

ICON_DIR = Path(__file__).resolve().parent / "icons"


def browser_icon(role):
    return QIcon(str(ICON_DIR / f"{role}.svg"))
