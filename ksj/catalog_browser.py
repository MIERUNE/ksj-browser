"""全データカタログのQGISブラウザ項目。配布ファイル展開時のみネットワークに接続する。"""

import hashlib
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

from qgis.core import (
    QgsApplication,
    QgsDataCollectionItem,
    QgsDataItem,
    QgsMimeDataUtils,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from . import catalog, zip_scanner
from .browser_icons import browser_icon

# 配布ファイルを年度 → 地域 → 市区町村の順に階層化する。
RESOURCE_DIMENSIONS = ("year", "region", "municipality")


def path_key(value):
    return quote(value, safe="")


def url_key(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def ordered(items):
    for order, item in enumerate(items):
        item.setSortKey(order)
    return items


def message_item(parent, text):
    item = QgsDataItem(QgsDataItem.Custom, parent, text, f"{parent.path()}/message")
    item.setIcon(browser_icon("info"))
    item.setToolTip(text)
    item.setState(QgsDataItem.Populated)
    return item


def link_actions(parent, links):
    actions = []
    for title, url in links:
        if not url:
            continue
        action = QAction(title, parent)
        action.triggered.connect(
            lambda checked=False, target=url: QDesktopServices.openUrl(QUrl(target))
        )
        actions.append(action)
    return actions


def add_layers(uris):
    """URIが示すレイヤーをプロジェクトへ追加し、1つでも追加できたかを返す。"""
    added = False
    for uri in uris:
        layer_type = QgsRasterLayer if uri.layerType == "raster" else QgsVectorLayer
        layer = layer_type(uri.uri, uri.name, uri.providerKey)
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            added = True
    return added


def layer_item(parent, name, path, uri):
    item_type = (
        KsjVectorContainerItem
        if PurePosixPath(uri).suffix.lower() in zip_scanner.MULTILAYER_EXTENSIONS
        else KsjZipFileItem
    )
    return item_type(parent, name, path, uri)


class KsjZipFileItem(QgsDataItem):
    """ベクタ・ラスタの単一レイヤーノード。"""

    def __init__(self, parent, name, path, vsi_file_path):
        QgsDataItem.__init__(self, QgsDataItem.Layer, parent, name, path)
        self.vsi_file_path = vsi_file_path
        extension = PurePosixPath(vsi_file_path).suffix.lower()
        if extension in zip_scanner.RASTER_EXTENSIONS:
            icon = "/mIconRaster.svg"
        elif extension == ".csv":
            icon = "/mIconTableLayer.svg"
        else:
            icon = "/mIconVector.svg"
        self.setIcon(QgsApplication.getThemeIcon(icon))
        self.setToolTip(f"{name}\nダブルクリック、またはマップへドラッグして追加")
        self.setState(QgsDataItem.Populated)

    def hasDragEnabled(self):
        return True

    def mimeUris(self):
        """ドラッグ&ドロップでレイヤーを追加"""
        is_raster = (
            PurePosixPath(self.vsi_file_path).suffix.lower()
            in zip_scanner.RASTER_EXTENSIONS
        )
        uri = QgsMimeDataUtils.Uri()
        uri.layerType = "raster" if is_raster else "vector"
        uri.providerKey = "gdal" if is_raster else "ogr"
        uri.name = self.name()
        uri.uri = self.vsi_file_path
        return [uri]

    def handleDoubleClick(self):
        """ダブルクリックでレイヤーを追加"""
        return add_layers(self.mimeUris())


class KsjVectorContainerItem(QgsDataCollectionItem):
    """GML等の複数レイヤーを持つファイル。個別選択と全レイヤー追加に対応する。"""

    def __init__(self, parent, name, path, vsi_file_path):
        super().__init__(parent, name, path)
        self.vsi_file_path = vsi_file_path
        self.sublayers = None
        self.setIcon(browser_icon("dataset"))
        self.setToolTip(
            f"{name}\n展開してレイヤーを選択、ダブルクリックですべて追加"
        )

    def _layers(self):
        # サブレイヤー列挙はリモートファイル全体の読み込みを伴うため、項目ごとに1回だけ行う。
        if self.sublayers is None:
            provider = QgsProviderRegistry.instance().providerMetadata("ogr")
            self.sublayers = (
                provider.querySublayers(self.vsi_file_path) if provider else []
            )
        return self.sublayers

    def createChildren(self):
        layers = self._layers()
        if not layers:
            return [
                message_item(
                    self,
                    "レイヤーを取得できません — 配布ファイルの右クリックから取得できます",
                )
            ]
        return [
            KsjZipFileItem(self, layer.name(), f"{self.path()}/{idx}", layer.uri())
            for idx, layer in enumerate(layers)
        ]

    def hasDragEnabled(self):
        return True

    def mimeUris(self):
        return [layer.toMimeUri() for layer in self._layers()]

    def handleDoubleClick(self):
        return add_layers(self.mimeUris())


def root_children(parent):
    try:
        index = catalog.load_index()
    except (OSError, ValueError) as exc:
        return [message_item(parent, f"カタログを読み込めません: {exc}")]
    groups = {}
    for dataset in index["datasets"]:
        # 現行形式は公式分類を直接表示。旧形式は版ごとにまとめ、その下で分類する。
        legacy = dataset["edition"] != catalog.CURRENT_EDITION
        name = dataset["edition"] if legacy else dataset["category"]
        groups.setdefault((name, legacy), []).append(dataset)
    items = ordered(
        [
            KsjCategoryItem(
                parent, name, f"{parent.path()}/{path_key(name)}", datasets, legacy
            )
            for (name, legacy), datasets in groups.items()
        ]
    )
    parent.setToolTip(
        "分類 → データ → 年度 → 地域の順に展開して探せます。\n"
        f"公式一覧 {index['dataset_count']:,}項目 / 配布 {index['resource_count']:,}ファイル\n"
        f"カタログ取得: {index['generated_at']}\n"
        f"未取得ページ: {len(index.get('errors', {}))}\n"
        "旧版の使用許諾条件は各データの公式説明ページで確認してください。"
    )
    return items


class KsjCategoryItem(QgsDataCollectionItem):
    def __init__(self, parent, name, path, datasets, subdivide=False):
        super().__init__(parent, f"{name}（{len(datasets)}項目）", path)
        self.datasets = datasets
        self.subdivide = subdivide
        self.setIcon(browser_icon("folder"))
        self.setToolTip(f"{name}\nデータセット: {len(datasets):,}項目")

    def createChildren(self):
        if self.subdivide:
            return ordered(
                [
                    KsjCategoryItem(
                        self, name, f"{self.path()}/{path_key(name)}", datasets
                    )
                    for name, datasets in catalog.group_resources(
                        self.datasets, "category"
                    ).items()
                ]
            )
        return ordered(
            [
                KsjDatasetItem(self, f"{self.path()}/{dataset['id']}", dataset)
                for dataset in self.datasets
            ]
        )


class KsjDatasetItem(QgsDataCollectionItem):
    def __init__(self, parent, path, dataset):
        super().__init__(parent, dataset["title"], path)
        self.dataset = dataset
        self.setIcon(browser_icon("dataset"))
        self.setToolTip(
            f"{dataset['title']}\n配布ファイル: {dataset['resource_count']:,}件\n"
            f"{dataset['source_url']}\n"
            f"最新版の利用条件: {dataset.get('license') or '公式説明を参照'}\n"
            f"未取得ページ: {len(dataset.get('issues', {}))}\n"
            "右クリックから公式の説明・属性定義・利用条件を開けます。"
        )

    def createChildren(self):
        try:
            data = catalog.load_dataset(self.dataset["id"])
        except (OSError, ValueError) as exc:
            return [message_item(self, f"データ定義を読み込めません: {exc}")]
        warnings = [
            KsjWebItem(
                self,
                f"取得未完了 — {PurePosixPath(urlsplit(url).path).name}: {error}",
                url,
            )
            for url, error in data.get("issues", {}).items()
        ]
        if not data["resources"] and not warnings:
            return [
                KsjWebItem(
                    self, "配布状況を公式ページで確認", self.dataset["source_url"]
                )
            ]
        return ordered(
            warnings + resource_items(self, data["resources"], RESOURCE_DIMENSIONS)
        )

    def actions(self, parent):
        return link_actions(
            parent,
            [("公式の説明・属性定義・利用条件を開く", self.dataset["source_url"])],
        )


def resource_items(parent, resources, dimensions):
    """残りの分類軸で配布ファイルを段階的にまとめ、軸が尽きたら個々のファイルを並べる。"""
    for depth, dimension in enumerate(dimensions):
        # 欠損ラベルを持つ軸は常に階層にする。それ以外は値を持つファイルがある時だけ。
        if dimension in catalog.MISSING_LABELS or any(
            r.get(dimension) for r in resources
        ):
            return [
                KsjResourceGroupItem(
                    parent,
                    name,
                    f"{parent.path()}/{path_key(name)}",
                    records,
                    dimensions[depth + 1 :],
                    dimension=dimension,
                )
                for name, records in catalog.group_resources(
                    resources, dimension
                ).items()
            ]
    return [
        KsjResourceItem(parent, f"{parent.path()}/{url_key(r['url'])}", r)
        for r in resources
    ]


class KsjResourceGroupItem(QgsDataCollectionItem):
    def __init__(self, parent, name, path, resources, dimensions=(), *, dimension=None):
        super().__init__(parent, name, path)
        self.resources = resources
        self.dimensions = dimensions
        self.setIcon(browser_icon("year" if dimension == "year" else "region"))
        self.setToolTip(f"{name}\n配布ファイル: {len(resources):,}件")

    def createChildren(self):
        return ordered(resource_items(self, self.resources, self.dimensions))


class KsjWebItem(QgsDataItem):
    def __init__(self, parent, title, url):
        super().__init__(
            QgsDataItem.Custom, parent, title, f"{parent.path()}/website/{url_key(url)}"
        )
        self.url = url
        self.setIcon(browser_icon("link"))
        self.setToolTip(f"{title}\nダブルクリックでブラウザを開く\n{url}")
        self.setState(QgsDataItem.Populated)

    def handleDoubleClick(self):
        return QDesktopServices.openUrl(QUrl(self.url))


class KsjResourceItem(QgsDataCollectionItem):
    def __init__(self, parent, path, resource):
        super().__init__(parent, catalog.resource_label(resource), path)
        self.resource = resource
        self.download_url = resource["url"]
        suffix = PurePosixPath(urlsplit(self.download_url).path).suffix.lower()
        self.setIcon(browser_icon("archive" if suffix in {".zip", ".lzh"} else "dataset"))
        hint = (
            "展開して読み込むレイヤーを選択"
            if suffix == ".zip" or suffix in zip_scanner.SUPPORTED_EXTENSIONS
            else "展開してダウンロード項目を表示"
        )
        self.setToolTip(
            "\n".join(
                [resource["filename"], hint]
                + [f"{k}: {v}" for k, v in resource.get("metadata", {}).items()]
                + [self.download_url, "右クリック: ダウンロード・公式説明"]
            )
        )

    def createChildren(self):
        suffix = PurePosixPath(urlsplit(self.download_url).path).suffix.lower()
        if suffix == ".zip":
            return archive_children(self, zip_scanner.vsi_zip_root(self.download_url))
        if suffix in zip_scanner.SUPPORTED_EXTENSIONS:
            return [
                layer_item(
                    self,
                    self.resource["filename"],
                    f"{self.path()}/layer",
                    f"/vsicurl/{self.download_url}",
                )
            ]
        return [KsjWebItem(self, "配布ファイルをダウンロード", self.download_url)]

    def actions(self, parent):
        return link_actions(
            parent,
            [
                ("配布ファイルをダウンロード", self.download_url),
                ("この版の公式説明・利用条件を開く", self.resource.get("source_url")),
            ],
        )


def archive_children(parent, vsi_root):
    try:
        supported = zip_scanner.filter_supported(
            zip_scanner.list_entries_recursive(vsi_root)
        )
    except Exception as exc:
        # ZipScanError（str() がユーザー向け文言）に加え、公開元・GDAL由来の
        # 想定外例外もブラウザのワーカースレッドへ漏らさない。
        return [message_item(parent, f"取得失敗: {exc} — 右クリックで公式ページを確認")]
    if not supported:
        return [
            message_item(
                parent, "直接読み込める形式なし — 右クリックで配布ファイルを取得"
            )
        ]
    return tree_children(parent, zip_scanner.build_tree(supported), vsi_root)


def tree_children(parent, node, vsi_root):
    items = []
    for child in node.children or []:
        name = zip_scanner.decode_entry_name(child.name)
        path = f"{parent.path()}/{path_key(child.name)}"
        if child.kind == "folder":
            item = KsjArchiveFolderItem(parent, name, path, child, vsi_root)
        elif child.extension.lower() == ".zip":
            item = KsjNestedArchiveItem(
                parent, name, path, f"/vsizip/{{{vsi_root}/{child.path}}}"
            )
        else:
            item = layer_item(parent, name, path, f"{vsi_root}/{child.path}")
        items.append(item)
    return items


class KsjArchiveFolderItem(QgsDataCollectionItem):
    def __init__(self, parent, name, path, node, vsi_root):
        super().__init__(parent, name, path)
        self.node = node
        self.vsi_root = vsi_root
        self.setIcon(browser_icon("folder"))

    def createChildren(self):
        return tree_children(self, self.node, self.vsi_root)


class KsjNestedArchiveItem(QgsDataCollectionItem):
    def __init__(self, parent, name, path, vsi_root):
        super().__init__(parent, name, path)
        self.vsi_root = vsi_root
        self.setIcon(browser_icon("archive"))

    def createChildren(self):
        return archive_children(self, self.vsi_root)
