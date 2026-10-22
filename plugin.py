from qgis.core import QgsApplication

from .ksj.browser import KsjDataItemProvider
from .ksj.mesh_index import cancel_pending

PLUGIN_NAME = "KSJ-Provider"


class Plugin:
    def __init__(self, iface):
        self.iface = iface
        self.win = self.iface.mainWindow()
        self.provider = None

    def initGui(self):
        """QGIS GUIの初期化時に呼ばれる"""
        # ブラウザアイテムプロバイダを登録
        self.provider = KsjDataItemProvider()
        QgsApplication.instance().dataItemProviderRegistry().addProvider(self.provider)

    def unload(self):
        """QGISからプラグインがアンロードされる際に呼ばれる"""
        cancel_pending()
        if self.provider:
            QgsApplication.instance().dataItemProviderRegistry().removeProvider(
                self.provider
            )
