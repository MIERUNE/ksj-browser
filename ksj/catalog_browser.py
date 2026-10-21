"""全データカタログのQGISブラウザ表示。配布ファイル展開時のみネットワークに接続する。"""

import hashlib
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

from qgis.core import QgsDataCollectionItem, QgsDataItem
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from . import catalog, zip_scanner
from .browser import KsjVectorContainerItem, KsjZipFileItem

MULTILAYER_EXTENSIONS = {".gml", ".xml", ".gpkg", ".kml"}


def layer_item(parent, name, path, uri):
    item_type = (
        KsjVectorContainerItem
        if PurePosixPath(uri).suffix.lower() in MULTILAYER_EXTENSIONS
        else KsjZipFileItem
    )
    return item_type(parent, name, path, uri)


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


def message_item(parent, text):
    item = QgsDataItem(QgsDataItem.Custom, parent, text, f"{parent.path()}/message")
    item.setState(QgsDataItem.Populated)
    return item


def path_key(value):
    return quote(value, safe="")


def ordered(items):
    for order, item in enumerate(items):
        item.setSortKey(order)
    return items


def root_children(parent):
    try:
        index = catalog.load_index()
    except (OSError, ValueError) as exc:
        return [message_item(parent, f"カタログを読み込めません: {exc}")]
    groups = {}
    for dataset in index["datasets"]:
        # 現行は公式分類を直接表示。旧形式は別の入口にまとめる。
        key = (
            dataset["category"]
            if dataset["edition"] == "現行形式"
            else dataset["edition"]
        )
        groups.setdefault(key, []).append(dataset)
    items = ordered(
        [
            KsjCategoryItem(parent, name, f"{parent.path()}/{path_key(name)}", datasets)
            for name, datasets in groups.items()
        ]
    )
    parent.setToolTip(
        f"公式一覧 {index['dataset_count']}項目 / 配布 {index['resource_count']}ファイル\n"
        f"カタログ取得: {index['generated_at']}\n"
        f"未取得ページ: {len(index.get('errors', {}))}\n"
        "旧版の使用許諾条件は各データの公式説明ページで確認してください。"
    )
    return items


class KsjCategoryItem(QgsDataCollectionItem):
    def __init__(self, parent, name, path, datasets, subdivide=True):
        super().__init__(parent, f"{name}（{len(datasets)}項目）", path)
        self.datasets = datasets
        self.subdivide = subdivide

    def createChildren(self):
        if self.subdivide and self.datasets[0]["edition"] != "現行形式":
            groups = {}
            for dataset in self.datasets:
                groups.setdefault(dataset["category"], []).append(dataset)
            return ordered(
                [
                    KsjCategoryItem(
                        self, name, f"{self.path()}/{path_key(name)}", datasets, False
                    )
                    for name, datasets in groups.items()
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
        super().__init__(
            parent, f"{dataset['title']}（{dataset['resource_count']}ファイル）", path
        )
        self.dataset = dataset
        self.setToolTip(
            f"{dataset['title']}\n{dataset['source_url']}\n"
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
            warnings
            + [
                KsjResourceGroupItem(
                    self, name, f"{self.path()}/{path_key(name)}", records, "region"
                )
                for name, records in catalog.group_resources(
                    data["resources"], "year"
                ).items()
            ]
        )

    def actions(self, parent):
        return link_actions(
            parent,
            [("公式の説明・属性定義・利用条件を開く", self.dataset["source_url"])],
        )


class KsjResourceGroupItem(QgsDataCollectionItem):
    def __init__(
        self,
        parent,
        name,
        path,
        resources,
        next_dimension=None,
        municipality_grouped=False,
    ):
        super().__init__(parent, f"{name}（{len(resources)}ファイル）", path)
        self.resources = resources
        self.next_dimension = next_dimension
        self.municipality_grouped = municipality_grouped

    def createChildren(self):
        if self.next_dimension:
            return ordered(
                [
                    KsjResourceGroupItem(
                        self, name, f"{self.path()}/{path_key(name)}", records
                    )
                    for name, records in catalog.group_resources(
                        self.resources, self.next_dimension
                    ).items()
                ]
            )
        if not self.municipality_grouped and any(
            r.get("municipality") for r in self.resources
        ):
            return ordered(
                [
                    KsjResourceGroupItem(
                        self,
                        name,
                        f"{self.path()}/{path_key(name)}",
                        records,
                        municipality_grouped=True,
                    )
                    for name, records in catalog.group_resources(
                        self.resources, "municipality"
                    ).items()
                ]
            )
        return ordered(
            [
                KsjResourceItem(
                    self,
                    f"{self.path()}/{hashlib.sha256(r['url'].encode()).hexdigest()[:16]}",
                    r,
                )
                for r in self.resources
            ]
        )


class KsjWebItem(QgsDataItem):
    def __init__(self, parent, title, url):
        key = hashlib.sha256(url.encode()).hexdigest()[:16]
        super().__init__(
            QgsDataItem.Custom, parent, title, f"{parent.path()}/website/{key}"
        )
        self.url = url
        self.setToolTip(url)
        self.setState(QgsDataItem.Populated)

    def handleDoubleClick(self):
        return QDesktopServices.openUrl(QUrl(self.url))


class KsjResourceItem(QgsDataCollectionItem):
    def __init__(self, parent, path, resource):
        super().__init__(parent, catalog.resource_label(resource), path)
        self.resource = resource
        self.download_url = resource["url"]
        self.setToolTip(
            "\n".join(
                [f"{k}: {v}" for k, v in resource.get("metadata", {}).items()]
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
        files = zip_scanner.list_entries_recursive(vsi_root)
        supported = zip_scanner.filter_supported(files)
        if not supported:
            return [
                message_item(
                    parent, "直接読み込める形式なし — 右クリックで配布ファイルを取得"
                )
            ]
        tree = zip_scanner.build_tree(supported)
        return tree_children(parent, tree, vsi_root)
    except zip_scanner.ZipScanError as exc:
        return [
            message_item(
                parent, f"取得失敗: {exc.user_message} — 右クリックで公式ページを確認"
            )
        ]
    except Exception as exc:
        # 公開元・GDAL由来の想定外例外をブラウザのワーカースレッドへ漏らさない。
        return [message_item(parent, f"取得失敗: {exc} — 右クリックで公式ページを確認")]


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

    def createChildren(self):
        return tree_children(self, self.node, self.vsi_root)


class KsjNestedArchiveItem(QgsDataCollectionItem):
    def __init__(self, parent, name, path, vsi_root):
        super().__init__(parent, name, path)
        self.vsi_root = vsi_root

    def createChildren(self):
        return archive_children(self, self.vsi_root)
