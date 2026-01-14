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
    QgsVectorLayer,
)

from . import data_loader, zip_scanner
from .zip_scanner import ZipScanError, decode_entry_name

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

        for idx, (collection_id, collection_data) in enumerate(collections.items()):
            collection_name = data_loader.get_data_collection_name(collection_id)
            path = f"{self.path()}/{collection_id}"
            item = KsjCollectionItem(
                self, collection_name, path, collection_id, collection_data
            )
            item.setSortKey(idx)
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

        for idx, (year, prefectures) in enumerate(self.collection_data.items()):
            path = f"{self.path()}/{year}"
            item = KsjYearItem(self, year, path, self.collection_id, year, prefectures)
            item.setSortKey(idx)
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

        for idx, (prefecture, filename) in enumerate(self.prefectures.items()):
            path = f"{self.path()}/{prefecture}"
            # 都道府県ノードをコレクションアイテムとして作成
            item = KsjPrefectureItem(
                self,
                prefecture,
                path,
                self.collection_id,
                self.year,
                prefecture,
                filename,
            )
            item.setSortKey(idx)
            children.append(item)

        return children


class KsjPrefectureItem(QgsDataCollectionItem):
    """都道府県ノード（コレクション）- ZIP内階層を展開"""

    def __init__(self, parent, name, path, collection_id, year, prefecture, filename):
        QgsDataCollectionItem.__init__(self, parent, name, path)
        self.collection_id = collection_id
        self.year = year
        self.prefecture = prefecture
        self.filename = filename

    def createChildren(self):
        """リモートZIPを走査し、ZIP内階層を生成"""
        try:
            # ダウンロードURLを構築
            download_url = data_loader.build_download_url(
                self.collection_id, self.year, self.filename
            )

            # VSI ZIPルートパスを取得
            vsi_zip_root = zip_scanner.vsi_zip_root(download_url)

            # ZIP内ファイルを再帰的に列挙
            all_files = zip_scanner.list_entries_recursive(vsi_zip_root)

            # 対象拡張子（.shp / .geojson）のみ抽出
            supported_files = zip_scanner.filter_supported(all_files)

            # 対象ファイルが無い場合
            if not supported_files:
                return self._create_empty_message()

            # ファイルパス一覧からフォルダ階層ツリーを生成
            zip_tree = zip_scanner.build_tree(supported_files)

            # ZipNodeツリーからブラウザアイテムを生成
            return self._create_items_from_tree(zip_tree, vsi_zip_root)

        except ZipScanError as e:
            # 走査失敗時はエラーメッセージアイテムを返す
            return self._create_error_message(e.user_message)
        except Exception as e:
            # 予期しないエラー
            return self._create_error_message(f"エラー: {str(e)}")

    def _create_items_from_tree(self, zip_node, vsi_zip_root):
        """ZipNodeツリーからブラウザアイテムを再帰的に生成"""
        items = []

        if zip_node.children is None:
            return items

        for idx, child in enumerate(zip_node.children):
            if child.kind == "folder":
                # フォルダノードを作成
                folder_path = f"{self.path()}/{child.path}"
                display_name = decode_entry_name(child.name)
                folder_item = KsjZipFolderItem(
                    self, display_name, folder_path, child, vsi_zip_root
                )
                folder_item.setSortKey(idx)
                items.append(folder_item)
            elif child.kind == "file" and child.is_supported:
                # 対象ファイルノードを作成
                file_path = f"{self.path()}/{child.path}"
                vsi_file_path = f"{vsi_zip_root}/{child.path}"
                display_name = decode_entry_name(child.name)
                file_item = KsjZipFileItem(self, display_name, file_path, vsi_file_path)
                file_item.setSortKey(idx)
                items.append(file_item)

        return items

    def _create_empty_message(self):
        """対象データなしメッセージアイテムを作成"""
        path = f"{self.path()}/empty"
        item = QgsDataItem(QgsDataItem.Custom, self, "対象データなし", path)
        item.setState(QgsDataItem.Populated)
        return [item]

    def _create_error_message(self, message):
        """エラーメッセージアイテムを作成"""
        path = f"{self.path()}/error"
        item = QgsDataItem(QgsDataItem.Error, self, f"エラー: {message}", path)
        item.setState(QgsDataItem.Populated)
        return [item]


class KsjZipFolderItem(QgsDataCollectionItem):
    """ZIP内フォルダノード"""

    def __init__(self, parent, name, path, zip_node, vsi_zip_root):
        QgsDataCollectionItem.__init__(self, parent, name, path)
        self.zip_node = zip_node
        self.vsi_zip_root = vsi_zip_root

    def createChildren(self):
        """子フォルダ/子ファイルを生成"""
        items = []

        if self.zip_node.children is None:
            return items

        for idx, child in enumerate(self.zip_node.children):
            if child.kind == "folder":
                # 子フォルダノード
                folder_path = f"{self.path()}/{child.name}"
                display_name = decode_entry_name(child.name)
                folder_item = KsjZipFolderItem(
                    self, display_name, folder_path, child, self.vsi_zip_root
                )
                folder_item.setSortKey(idx)
                items.append(folder_item)
            elif child.kind == "file" and child.is_supported:
                # 子ファイルノード
                file_path = f"{self.path()}/{child.name}"
                vsi_file_path = f"{self.vsi_zip_root}/{child.path}"
                display_name = decode_entry_name(child.name)
                file_item = KsjZipFileItem(self, display_name, file_path, vsi_file_path)
                file_item.setSortKey(idx)
                items.append(file_item)

        return items


class KsjZipFileItem(QgsDataItem):
    """ZIP内ファイルノード（.shp / .geojson）"""

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
        layer_name = PurePosixPath(self.vsi_file_path).name

        uri = QgsMimeDataUtils.Uri()
        uri.layerType = "vector"
        uri.providerKey = "ogr"
        uri.name = layer_name
        uri.uri = self.vsi_file_path

        return [uri]

    def handleDoubleClick(self):
        """ダブルクリックでレイヤーを追加"""
        layer_name = PurePosixPath(self.vsi_file_path).name

        # レイヤーを作成して追加
        layer = QgsVectorLayer(self.vsi_file_path, layer_name, "ogr")

        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            return True

        return False
