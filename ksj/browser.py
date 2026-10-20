"""QGISブラウザパネルでKSJデータを表示するためのアイテム群"""

from pathlib import PurePosixPath

from qgis.core import (
    QgsApplication,
    QgsDataCollectionItem,
    QgsDataItem,
    QgsDataItemProvider,
    QgsDataProvider,
    QgsMimeDataUtils,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorLayer,
)

from . import zip_scanner

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
        from .catalog_browser import root_children

        return root_children(self)


class KsjZipFileItem(QgsDataItem):
    """ベクタ・ラスタの単一レイヤーノード。"""

    def __init__(self, parent, name, path, vsi_file_path):
        QgsDataItem.__init__(self, QgsDataItem.Layer, parent, name, path)
        self.vsi_file_path = vsi_file_path

        # レイヤーアイコンを設定
        icon = QgsApplication.getThemeIcon("/mIconVirtualLayer.svg")
        self.setIcon(icon)

        self.setState(QgsDataItem.Populated)

    def hasDragEnabled(self):
        return True

    def mimeUris(self):
        """ドラッグ&ドロップでレイヤーを追加"""
        layer_name = self.name()

        uri = QgsMimeDataUtils.Uri()
        is_raster = (
            PurePosixPath(self.vsi_file_path).suffix.lower()
            in zip_scanner.RASTER_EXTENSIONS
        )
        uri.layerType = "raster" if is_raster else "vector"
        uri.providerKey = "gdal" if is_raster else "ogr"
        uri.name = layer_name
        uri.uri = self.vsi_file_path

        return [uri]

    def handleDoubleClick(self):
        """ダブルクリックでレイヤーを追加"""
        layer_name = self.name()

        # レイヤーを作成して追加
        if (
            PurePosixPath(self.vsi_file_path).suffix.lower()
            in zip_scanner.RASTER_EXTENSIONS
        ):
            layer = QgsRasterLayer(self.vsi_file_path, layer_name, "gdal")
        else:
            layer = QgsVectorLayer(self.vsi_file_path, layer_name, "ogr")

        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            return True

        return False


class KsjVectorContainerItem(QgsDataCollectionItem):
    """GML等の複数レイヤーを持つファイル。個別選択と全レイヤー追加に対応する。"""

    def __init__(self, parent, name, path, vsi_file_path):
        super().__init__(parent, name, path)
        self.vsi_file_path = vsi_file_path

    def _layers(self):
        provider = QgsProviderRegistry.instance().providerMetadata("ogr")
        return provider.querySublayers(self.vsi_file_path) if provider else []

    def createChildren(self):
        layers = self._layers()
        if not layers:
            item = QgsDataItem(
                QgsDataItem.Custom,
                self,
                "レイヤーを取得できません — 配布ファイルの右クリックから取得できます",
                f"{self.path()}/empty",
            )
            item.setState(QgsDataItem.Populated)
            return [item]
        return [
            KsjZipFileItem(self, layer.name(), f"{self.path()}/{idx}", layer.uri())
            for idx, layer in enumerate(layers)
        ]

    def hasDragEnabled(self):
        return True

    def mimeUris(self):
        uris = []
        for layer in self._layers():
            uri = QgsMimeDataUtils.Uri()
            uri.layerType = "vector"
            uri.providerKey = "ogr"
            uri.name = layer.name()
            uri.uri = layer.uri()
            uris.append(uri)
        return uris

    def handleDoubleClick(self):
        added = False
        for uri in self.mimeUris():
            layer = QgsVectorLayer(uri.uri, uri.name, uri.providerKey)
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                added = True
        return added
