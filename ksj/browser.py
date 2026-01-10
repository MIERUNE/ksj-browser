"""QGISブラウザパネルでKSJデータを表示するためのアイテム群"""

from qgis.core import (
    QgsApplication,
    QgsDataCollectionItem,
    QgsDataItem,
    QgsDataItemProvider,
    QgsDataProvider,
    QgsMimeDataUtils,
    QgsProject,
    QgsVectorLayer,
)

from . import data_loader

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
        """各データコレクションをルート直下に表示"""
        children = []
        collections = data_loader.load_data_collections()

        for collection_id, collection_data in collections.items():
            collection_name = data_loader.get_data_collection_name(collection_id)
            path = f"{self.path()}/{collection_id}"
            item = KsjCollectionItem(
                self, collection_name, path, collection_id, collection_data
            )
            children.append(item)

        return children


class KsjCollectionItem(QgsDataCollectionItem):
    """各データコレクション（例: 土砂災害警戒区域）"""

    def __init__(self, parent, name, path, collection_id, collection_data):
        QgsDataCollectionItem.__init__(self, parent, name, path)
        self.collection_id = collection_id
        self.collection_data = collection_data

    def createChildren(self):
        """年度ごとにグループ化"""
        children = []

        for year, prefectures in self.collection_data.items():
            path = f"{self.path()}/{year}"
            item = KsjYearItem(self, year, path, self.collection_id, year, prefectures)
            children.append(item)

        return children


class KsjYearItem(QgsDataCollectionItem):
    """年度アイテム（例: 2024年）"""

    def __init__(self, parent, name, path, collection_id, year, prefectures):
        QgsDataCollectionItem.__init__(self, parent, name, path)
        self.collection_id = collection_id
        self.year = year
        self.prefectures = prefectures

    def createChildren(self):
        """都道府県ごとにアイテムを作成"""
        children = []

        for prefecture, filename in self.prefectures.items():
            path = f"{self.path()}/{prefecture}"
            item = KsjDataItem(
                self,
                prefecture,
                path,
                self.collection_id,
                self.year,
                prefecture,
                filename,
            )
            children.append(item)

        return children


class KsjDataItem(QgsDataItem):
    """実際のデータファイルアイテム"""

    def __init__(self, parent, name, path, collection_id, year, prefecture, filename):
        QgsDataItem.__init__(self, QgsDataItem.Collection, parent, name, path)
        self.collection_id = collection_id
        self.year = year
        self.prefecture = prefecture
        self.filename = filename

        # ポリゴンアイコンを設定
        icon = QgsApplication.getThemeIcon("/mIconPolygonLayer.svg")
        self.setIcon(icon)

        # populate()を呼ぶことで子要素の有無を判定し、子要素がない場合はトグルを非表示
        self.populate()

    def hasDragEnabled(self):
        return True

    def mimeUris(self):
        """ドラッグ&ドロップでレイヤーを追加"""
        download_url = data_loader.build_download_url(
            self.collection_id, self.year, self.filename
        )
        shapefile_path = data_loader.get_shapefile_path_in_zip(self.year, self.filename)

        # GDAL VFS形式でURIを構築
        vsi_url = f"/vsizip//vsicurl/{download_url}"
        full_path = f"{vsi_url}/{shapefile_path}"

        uri = QgsMimeDataUtils.Uri()
        uri.layerType = "vector"
        uri.providerKey = "ogr"
        uri.name = f"{self.prefecture} ({self.year})"
        uri.uri = full_path

        return [uri]

    def handleDoubleClick(self):
        """ダブルクリックでレイヤーを追加"""
        download_url = data_loader.build_download_url(
            self.collection_id, self.year, self.filename
        )
        shapefile_path = data_loader.get_shapefile_path_in_zip(self.year, self.filename)

        # GDAL VFS形式でURIを構築
        vsi_url = f"/vsizip//vsicurl/{download_url}"
        full_path = f"{vsi_url}/{shapefile_path}"

        # レイヤー名
        layer_name = f"{self.prefecture} ({self.year})"

        # レイヤーを作成して追加
        layer = QgsVectorLayer(full_path, layer_name, "ogr")

        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            return True

        return False
