from qgis.core import QgsApplication, QgsProject

from .ksj.browser import KsjDataItemProvider
from .ksj.mesh_index import cancel_pending
from .ksj import layer_loading
from .ksj.processing_provider import KsjProcessingProvider

PLUGIN_NAME = "KSJ-Provider"


class Plugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.processing_provider = None
        self.drop_handler = None

    def initProcessing(self):
        """GUIとqgis_processの両方で呼べる。二重登録はしない。"""
        if self.processing_provider is None:
            provider = KsjProcessingProvider()
            if QgsApplication.processingRegistry().addProvider(provider):
                self.processing_provider = provider

    def initGui(self):
        """QGIS GUIの初期化時に呼ばれる"""
        self.initProcessing()
        if self.drop_handler is None and self.iface is not None:
            self.drop_handler = layer_loading.KsjDropHandler()
            self.iface.registerCustomDropHandler(self.drop_handler)
            QgsProject.instance().cleared.connect(layer_loading.cancel_pending)
        # ブラウザアイテムプロバイダを登録
        if self.provider is None:
            self.provider = KsjDataItemProvider()
            QgsApplication.instance().dataItemProviderRegistry().addProvider(
                self.provider
            )

    def unload(self):
        """QGISからプラグインがアンロードされる際に呼ばれる"""
        cancel_pending()
        layer_loading.cancel_pending()
        if self.drop_handler is not None:
            self.iface.unregisterCustomDropHandler(self.drop_handler)
            QgsProject.instance().cleared.disconnect(layer_loading.cancel_pending)
            self.drop_handler = None
        if self.processing_provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.processing_provider)
            self.processing_provider = None
        if self.provider:
            QgsApplication.instance().dataItemProviderRegistry().removeProvider(
                self.provider
            )
            self.provider = None
