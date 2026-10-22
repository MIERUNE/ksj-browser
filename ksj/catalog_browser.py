"""全データカタログのブラウザ項目。未取得の配布ファイルだけを保存して読み込む。"""

from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

from qgis.core import (
    QgsApplication,
    QgsDataCollectionItem,
    QgsDataItem,
    QgsErrorItem,
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

from . import catalog, local_storage, zip_scanner
from .browser_icons import browser_icon
from .mesh_index import add_mesh_index

# 配布ファイルを年度 → 地域 → 市区町村の順に階層化する。
RESOURCE_DIMENSIONS = ("year", "region", "municipality")


def path_key(value):
    return quote(value, safe="")


def ordered(items):
    for order, item in enumerate(items):
        item.setSortKey(order)
    return items


def message_item(parent, text, *, error=False):
    path = f"{parent.path()}/message"
    if error:
        item = QgsErrorItem(parent, text, path)
    else:
        item = QgsDataItem(QgsDataItem.Custom, parent, text, path)
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


def repopulate(item):
    """保存先の変更後に項目の子を作り直す。地図のレイヤーには触れない。"""
    # refreshだけでは同じブラウザパスの子が再利用され、古いURIが残る。
    item.depopulate()
    item.refresh()


def storage_actions(item, parent):
    """保存先の操作はGUIスレッドで実行する。"""
    change = QAction("データの保存先を変更…", parent)

    def choose():
        if local_storage.choose_download_directory(parent):
            repopulate(item)

    change.triggered.connect(choose)
    actions = [change]
    directory = local_storage.download_directory()
    if directory:
        open_folder = QAction("データの保存先を開く", parent)
        open_folder.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(directory))
        )
        actions.append(open_folder)
    return actions


class KsjStorageSetupItem(QgsDataItem):
    """ワーカーでダイアログを開かず、初回だけGUI操作へ案内する。"""

    def __init__(self, parent):
        super().__init__(
            QgsDataItem.Custom,
            parent,
            "保存先を選択してダウンロード…",
            f"{parent.path()}/storage",
        )
        self.setIcon(browser_icon("folder"))
        self.setToolTip("ダブルクリックで保存先を選択。次回からは自動で再利用します。")
        self.setState(QgsDataItem.Populated)

    def handleDoubleClick(self):
        if local_storage.choose_download_directory():
            repopulate(self.parent())
        return True


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
        if Path(uri).suffix.lower() in zip_scanner.MULTILAYER_EXTENSIONS
        else KsjFileItem
    )
    return item_type(parent, name, path, uri)


class KsjFileItem(QgsDataItem):
    """ベクタ・ラスタの単一レイヤーノード。"""

    def __init__(self, parent, name, path, file_path):
        QgsDataItem.__init__(self, QgsDataItem.Layer, parent, name, path)
        self.file_path = file_path
        extension = Path(file_path).suffix.lower()
        self.is_raster = zip_scanner.provider_key(file_path) == "gdal"
        if self.is_raster:
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
        uri = QgsMimeDataUtils.Uri()
        uri.layerType = "raster" if self.is_raster else "vector"
        uri.providerKey = "gdal" if self.is_raster else "ogr"
        uri.name = self.name()
        uri.uri = self.file_path
        return [uri]

    def handleDoubleClick(self):
        """ダブルクリックでレイヤーを追加"""
        return add_layers(self.mimeUris())


class KsjVectorContainerItem(QgsDataCollectionItem):
    """GML等の複数レイヤーを持つファイル。個別選択と全レイヤー追加に対応する。"""

    def __init__(self, parent, name, path, file_path):
        super().__init__(parent, name, path)
        self.file_path = file_path
        self.sublayers = None
        self.layer_error = None
        self.setIcon(browser_icon("dataset"))
        self.setToolTip(f"{name}\n展開してレイヤーを選択、ダブルクリックですべて追加")

    def _layers(self):
        # サブレイヤー列挙はファイル全体の読み込みを伴うため、項目ごとに1回だけ行う。
        if self.sublayers is None:
            try:
                provider = QgsProviderRegistry.instance().providerMetadata("ogr")
                self.sublayers = (
                    provider.querySublayers(self.file_path) if provider else []
                )
            except Exception as exc:
                # プロバイダ由来の例外をQGISのワーカーやドラッグ処理へ漏らさない。
                # 失敗も保持し、再取得は配布ファイル側の再読み込みで行う。
                self.sublayers = []
                self.layer_error = str(exc)
        return self.sublayers

    def createChildren(self):
        layers = self._layers()
        if self.layer_error is not None:
            return [
                message_item(
                    self,
                    f"レイヤーの取得失敗: {self.layer_error} — 配布ファイルを再読み込みしてください",
                    error=True,
                )
            ]
        if not layers:
            return [
                message_item(
                    self,
                    "レイヤーを取得できません — 配布ファイルの右クリックから取得できます",
                )
            ]
        return [
            KsjFileItem(self, layer.name(), f"{self.path()}/{idx}", layer.uri())
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
    except catalog.CatalogError as exc:
        return [message_item(parent, f"カタログを読み込めません: {exc}", error=True)]
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
        except catalog.CatalogError as exc:
            return [
                message_item(self, f"データ定義を読み込めません: {exc}", error=True)
            ]
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
        KsjResourceItem(parent, f"{parent.path()}/{local_storage.url_key(r['url'])}", r)
        for r in resources
    ]


class KsjResourceGroupItem(QgsDataCollectionItem):
    def __init__(self, parent, name, path, resources, dimensions=(), *, dimension=None):
        super().__init__(parent, name, path)
        self.resources = resources
        self.dimensions = dimensions
        # 索引は年度単位で作る。判定は項目の生成時に1回だけ行う。
        self.has_mesh = dimension == "year" and any(
            catalog.mesh_code(r) for r in resources
        )
        self.setIcon(browser_icon("year" if dimension == "year" else "region"))
        self.setToolTip(f"{name}\n配布ファイル: {len(resources):,}件")
        if self.has_mesh:
            self.setToolTip(
                self.toolTip() + "\n右クリックでメッシュ索引を地図に追加できます。"
            )

    def createChildren(self):
        return ordered(resource_items(self, self.resources, self.dimensions))

    def actions(self, parent):
        if not self.has_mesh:
            return []
        action = QAction("メッシュ索引を地図に追加", parent)
        # QActionはGUIスレッドで実行される。createChildrenでは地図を操作しない。
        dataset = self.parent()
        title = f"{dataset.name()} {self.name()}" if dataset else self.name()
        action.triggered.connect(
            lambda checked=False: add_mesh_index(title, self.resources)
        )
        return [action]


class KsjWebItem(QgsDataItem):
    def __init__(self, parent, title, url):
        super().__init__(
            QgsDataItem.Custom,
            parent,
            title,
            f"{parent.path()}/website/{local_storage.url_key(url)}",
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
        self.suffix = zip_scanner.download_suffix(self.download_url)
        self.setIcon(
            browser_icon("archive" if self.suffix in {".zip", ".lzh"} else "dataset")
        )
        hint = (
            "展開するとデータを取得・解凍し、保存済みのファイルは再利用します"
            if self.suffix in zip_scanner.SUPPORTED_EXTENSIONS
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
        if self.suffix not in zip_scanner.SUPPORTED_EXTENSIONS:
            return [KsjWebItem(self, "配布ファイルをダウンロード", self.download_url)]
        directory = local_storage.download_directory()
        if not directory:
            return [KsjStorageSetupItem(self)]
        try:
            local_path = local_storage.ensure_local_data(self.download_url, directory)
            if self.suffix == ".zip":
                return directory_children(self, local_path)
            return [
                layer_item(
                    self, self.resource["filename"], f"{self.path()}/layer", local_path
                )
            ]
        except Exception as exc:
            # DownloadError・ZipScanError（str() が利用者向け文言）に加え、公開元・
            # GDAL由来の想定外例外もブラウザのワーカースレッドへ漏らさない。
            return [
                message_item(self, f"取得失敗: {exc} — 右クリックで再試行", error=True)
            ]

    def actions(self, parent):
        retry = QAction("再読み込み（保存済みデータを再利用）", parent)
        retry.triggered.connect(lambda: repopulate(self))
        return (
            [retry]
            + storage_actions(self, parent)
            + link_actions(
                parent,
                [
                    ("配布ファイルをダウンロード", self.download_url),
                    (
                        "この版の公式説明・利用条件を開く",
                        self.resource.get("source_url"),
                    ),
                ],
            )
        )


def directory_children(parent, root_path):
    supported = zip_scanner.supported_entries(root_path)
    if not supported:
        return [
            message_item(
                parent, "直接読み込める形式なし — 右クリックで配布ファイルを取得"
            )
        ]
    return tree_children(parent, zip_scanner.build_tree(supported), root_path)


def tree_children(parent, node, root_path):
    root = Path(root_path)
    items = []
    for child in node.children or []:
        path = f"{parent.path()}/{path_key(child.name)}"
        if child.kind == "folder":
            items.append(KsjFolderItem(parent, child.name, path, child, root_path))
        else:
            items.append(layer_item(parent, child.name, path, str(root / child.path)))
    return items


class KsjFolderItem(QgsDataCollectionItem):
    def __init__(self, parent, name, path, node, root_path):
        super().__init__(parent, name, path)
        self.node = node
        self.root_path = root_path
        self.setIcon(browser_icon("folder"))

    def createChildren(self):
        return tree_children(self, self.node, self.root_path)
