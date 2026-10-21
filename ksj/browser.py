"""QGISブラウザパネルへKSJカタログを登録するプロバイダとルート項目"""

from qgis.core import QgsDataCollectionItem, QgsDataItemProvider, QgsDataProvider

from .catalog_browser import root_children

PROVIDER_KEY = "ksj"


class KsjDataItemProvider(QgsDataItemProvider):
    """KSJブラウザアイテムのプロバイダ"""

    def name(self):
        return "KSJ Provider"

    def capabilities(self):
        return QgsDataProvider.Net

    def createDataItem(self, path, parent):
        if path == "":
            return KsjRootItem()
        return None


class KsjRootItem(QgsDataCollectionItem):
    """KSJデータのルートアイテム"""

    def __init__(self):
        QgsDataCollectionItem.__init__(self, None, "国土数値情報（KSJ）", "/ksj")

    def createChildren(self):
        """公式分類に沿った全データカタログを表示する。"""
        return root_children(self)
