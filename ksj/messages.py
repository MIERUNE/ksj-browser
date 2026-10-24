"""メッセージログとメッセージバーへの通知。GUI の有無を問わず呼べる。"""

from qgis import utils
from qgis.core import Qgis, QgsMessageLog

LOG_TAG = "KSJ"


def log_message(message, warning=False):
    """KSJタグでメッセージログに残し、使った水準を返す。ワーカースレッドからも呼べる。"""
    level = Qgis.MessageLevel.Warning if warning else Qgis.MessageLevel.Info
    QgsMessageLog.logMessage(message, LOG_TAG, level)
    return level


def notify(message, warning=False):
    """ログに残したうえで、GUIがあればメッセージバーにも表示する。"""
    level = log_message(message, warning)
    if utils.iface is not None:
        utils.iface.messageBar().pushMessage(LOG_TAG, message, level=level, duration=8)


def main_window():
    """ダイアログの親。ヘッドレス環境やテストでは None。"""
    return utils.iface.mainWindow() if utils.iface is not None else None
