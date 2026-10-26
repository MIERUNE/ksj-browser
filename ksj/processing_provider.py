"""国土数値情報の検索・取得を公開する Processing プロバイダ。"""

from qgis.core import QgsProcessingProvider

from .browser_icons import plugin_icon
from .processing_algorithms import (
    DownloadResource,
    ListResources,
    LoadLayer,
    SearchDatasets,
)


class KsjProcessingProvider(QgsProcessingProvider):
    def id(self):
        return "ksj"

    def name(self):
        return "国土数値情報"

    def icon(self):
        return plugin_icon()

    def loadAlgorithms(self):
        for algorithm in (SearchDatasets, ListResources, DownloadResource, LoadLayer):
            self.addAlgorithm(algorithm())
