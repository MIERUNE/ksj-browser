"""QGISブラウザパネルへKSJカタログを登録するプロバイダとルート項目"""

from qgis.core import QgsDataCollectionItem, QgsDataItemProvider, QgsDataProvider

from . import catalog
from .catalog_browser import root_children, storage_actions
from .browser_icons import browser_icon

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
        self.setIcon(browser_icon("catalog"))
        tooltip = (
            "分類 → データ → 年度 → 地域の順に展開して探せます。\n"
            "データは初回だけ指定した保存先へ取得します。右クリックで保存先を変更できます。"
        )
        try:
            index = catalog.load_index()
            tooltip += (
                f"\n公式一覧 {index['dataset_count']:,}項目 / 配布 {index['resource_count']:,}ファイル\n"
                f"カタログ取得: {index['generated_at']}\n"
                f"未取得ページ: {len(index.get('errors', {}))}\n"
                "旧版の使用許諾条件は各データの公式説明ページで確認してください。"
            )
        except (catalog.CatalogError, KeyError, TypeError, ValueError) as exc:
            # 概要が不完全でもルートと保存先の操作は利用できるようにする。
            tooltip += f"\nカタログの概要を読み込めません: {exc}"
        self.setToolTip(tooltip)

    def createChildren(self):
        """公式分類に沿った全データカタログを表示する。"""
        return root_children(self)

    def actions(self, parent):
        return storage_actions(self, parent)
