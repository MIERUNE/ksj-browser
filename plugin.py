from qgis.core import QgsApplication

from .ksj.browser import KsjDataItemProvider
from .ksj.mesh_index import cancel_pending
from .ksj.processing_provider import KsjProcessingProvider

PLUGIN_NAME = "KSJ-Provider"


class Plugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.processing_provider = None

    def initProcessing(self):
        """GUIとqgis_processの両方で呼べる。二重登録はしない。"""
        if self.processing_provider is None:
            provider = KsjProcessingProvider()
            if QgsApplication.processingRegistry().addProvider(provider):
                self.processing_provider = provider

    def initGui(self):
        """QGIS GUIの初期化時に呼ばれる"""
        self.initProcessing()
        # ブラウザアイテムプロバイダを登録
        if self.provider is None:
            self.provider = KsjDataItemProvider()
            QgsApplication.instance().dataItemProviderRegistry().addProvider(
                self.provider
            )

    def unload(self):
        """QGISからプラグインがアンロードされる際に呼ばれる"""
        cancel_pending()
        if self.processing_provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.processing_provider)
            self.processing_provider = None
        if self.provider:
            QgsApplication.instance().dataItemProviderRegistry().removeProvider(
                self.provider
            )
            self.provider = None
