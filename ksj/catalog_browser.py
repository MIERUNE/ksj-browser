"""全データカタログのブラウザ項目。未取得の配布ファイルだけを保存して読み込む。"""

from functools import lru_cache
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

from qgis.core import (
    QgsAnimatedIcon,
    QgsApplication,
    QgsDataCollectionItem,
    QgsDataItem,
    QgsErrorItem,
)
from qgis.PyQt.QtCore import QEvent, QMetaObject, Qt, QThread, QUrl, pyqtSlot
from qgis.PyQt.QtGui import QDesktopServices

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from . import catalog, layer_loading, local_storage, remote_zip, zip_scanner
from .browser_icons import browser_icon, file_icon
from .mesh_index import add_mesh_index

# 配布ファイルを年度 → 地域 → 市区町村の順に階層化する。
RESOURCE_DIMENSIONS = ("year", "region", "municipality")
# 年度の右クリックメニューと先頭の子項目で同じ操作名を使う。
MESH_INDEX_LABEL = "メッシュ索引を地図に追加"
# ファイル項目のツールチップ。ファイル名の次の行に付ける。
ADD_HINT = "ダブルクリック、右クリック、またはマップへドラッグして追加\n追加方法・保存先の設定に従います"
LOADING_HINT = "読み込み中… データを取得して地図への追加を準備しています。"
# QObject::connect の SLOT() 表記。先頭の 1 はスロットを示す。
LOADING_FRAME_SLOT = "1update_loading_icon()"


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
    """再試行でZIPの一覧を取得し直す。地図のレイヤーには触れない。"""
    item.depopulate()
    item.refresh()


def storage_actions(parent):
    """保存先の操作はGUIスレッドで実行する。"""
    change = QAction("追加方法・保存先を設定…", parent)

    def choose():
        local_storage.configure_loading(parent)

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


class KsjLoadingSettingsItem(QgsDataItem):
    """現在の追加方法・保存先を常時表示し、ダブルクリックで変更する。"""

    def __init__(self, parent):
        super().__init__(
            QgsDataItem.Custom,
            parent,
            "追加方法・保存先",
            f"{parent.path()}/settings",
        )
        self.setIcon(browser_icon("settings"))
        self.update_label()
        local_storage.loading_settings_signals.changed.connect(self.update_label)
        self.setState(QgsDataItem.Populated)

    @pyqtSlot()
    def update_label(self):
        temporary = local_storage.loading_mode() == "temporary"
        directory = local_storage.download_directory()
        if temporary:
            title = "追加方法: 一時レイヤー（フォルダに保存しない）"
        elif directory:
            title = f"追加方法: 保存して追加 — {directory}"
        else:
            title = "追加方法: 保存して追加（保存先未設定）"
        self.setName(title)
        self.setToolTip(title + "\nダブルクリックで追加方法・保存先を変更")

    def handleDoubleClick(self):
        local_storage.configure_loading()
        return True


def root_children(parent):
    settings = KsjLoadingSettingsItem(parent)
    try:
        index = catalog.load_index()
    except catalog.CatalogError as exc:
        return [
            settings,
            message_item(parent, f"カタログを読み込めません: {exc}", error=True),
        ]
    groups = {}
    for dataset in index["datasets"]:
        # 現行形式は公式分類を直接表示。旧形式は版ごとにまとめ、その下で分類する。
        legacy = dataset["edition"] != catalog.CURRENT_EDITION
        name = dataset["edition"] if legacy else dataset["category"]
        groups.setdefault((name, legacy), []).append(dataset)
    return ordered(
        [settings]
        + [
            KsjCategoryItem(
                parent, name, f"{parent.path()}/{path_key(name)}", datasets, legacy
            )
            for (name, legacy), datasets in groups.items()
        ]
    )


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
        tooltip = f"{name}\n配布ファイル: {len(resources):,}件"
        if self.has_mesh:
            tooltip += f"\n展開して「{MESH_INDEX_LABEL}」をダブルクリックできます。"
        self.setToolTip(tooltip)

    def createChildren(self):
        index = [KsjMeshIndexItem(self)] if self.has_mesh else []
        return ordered(index + resource_items(self, self.resources, self.dimensions))

    def actions(self, parent):
        if not self.has_mesh:
            return []
        action = QAction(MESH_INDEX_LABEL, parent)
        action.setIcon(browser_icon("mesh-index"))
        action.triggered.connect(self.add_index)
        return [action]

    def add_index(self):
        # メニューとダブルクリックからGUIスレッドで実行する。年度の親は常にデータセット。
        add_mesh_index(f"{self.parent().name()} {self.name()}", self.resources)


class KsjMeshIndexItem(QgsDataItem):
    """年度の先頭に表示する、メッシュ索引を追加する操作項目。"""

    def __init__(self, parent):
        super().__init__(
            QgsDataItem.Custom, parent, MESH_INDEX_LABEL, f"{parent.path()}/mesh-index"
        )
        self.setIcon(browser_icon("mesh-index"))
        self.setToolTip(
            "ダブルクリックで、この年度の配布メッシュの枠と番号を地図に追加します。"
        )
        self.setState(QgsDataItem.Populated)

    def handleDoubleClick(self):
        self.parent().add_index()
        return True


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
        self.setIcon(file_icon(urlsplit(self.download_url).path))
        hint = (
            "展開してファイル名を表示。データ本体はレイヤー追加時に取得します"
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
        try:
            if self.suffix == ".zip":
                names = remote_zip.list_members(
                    self.download_url, local_storage.download_directory()
                )
                supported = [n for n in names if zip_scanner.is_supported_entry(n)]
                if not supported:
                    return [
                        message_item(
                            self,
                            "直接読み込める形式なし — 右クリックで配布ファイルを取得",
                        )
                    ]
                return remote_children(
                    self, zip_scanner.build_tree(supported), self.download_url
                )
            return [
                KsjFileItem(
                    self,
                    self.resource["filename"],
                    f"{self.path()}/layer",
                    self.download_url,
                    "",
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
            + storage_actions(parent)
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


@lru_cache(maxsize=None)
def loading_icon():
    """読み込み中の回転アイコン。QGIS本体と同様に1つを全項目で共有する。"""
    return QgsAnimatedIcon(
        QgsApplication.iconPath("mIconLoading.gif"), QgsApplication.instance()
    )


class KsjFileItem(QgsDataItem):
    """URIを組み立てる段階では取得せず、追加時に保存方式を適用する。

    name() は読み込み中の表示に書き換わるため、ファイルの同一性には filename を使う。
    """

    def __init__(self, parent, name, path, url, member):
        # QgsLayerItemではないため、標準レイヤー用メニューの対象にしない。
        super().__init__(QgsDataItem.Custom, parent, name, path)
        self.default_icon = file_icon(member or name)
        self.setIcon(self.default_icon)
        self.loading = False
        self.setState(QgsDataItem.Populated)
        self.url, self.member = url, member
        self.filename = name
        self.setSortKey(name)
        self.setToolTip(f"{name}\n{ADD_HINT}")
        layer_loading.loading_signals.changed.connect(self.update_loading)
        self.update_loading()

    def event(self, event):
        if event.type() == QEvent.Type.ThreadChange and layer_loading.pending:
            # ThreadChange は移動前に届く。予約した呼び出しは移動先で処理される。
            QMetaObject.invokeMethod(
                self, "update_loading", Qt.ConnectionType.QueuedConnection
            )
        return super().event(event)

    @pyqtSlot()
    def update_loading(self):
        if not self.loading and not layer_loading.pending:
            return
        # 一覧作成中にワーカーのイベントループが回っても描画を始めない。
        if QThread.currentThread() != QgsApplication.instance().thread():
            return
        busy = layer_loading.is_loading(self.url, self.member)
        if self.loading == busy:
            return
        self.loading = busy
        # Populating は子項目の展開矢印も表示するため、アニメーションだけを使う。
        if busy:
            loading_icon().connectFrameChanged(self, LOADING_FRAME_SLOT)
        else:
            loading_icon().disconnectFrameChanged(self, LOADING_FRAME_SLOT)
            self.setIcon(self.default_icon)
        self.setToolTip(f"{self.filename}\n{LOADING_HINT if busy else ADD_HINT}")
        self.setName(f"読み込み中… {self.filename}" if busy else self.filename)

    @pyqtSlot()
    def update_loading_icon(self):
        self.setIcon(loading_icon().icon())
        self.updateIcon()

    def hasDragEnabled(self):
        return True

    def mimeUris(self):
        return [layer_loading.drop_uri(self.url, self.member, self.filename)]

    def handleDoubleClick(self):
        layer_loading.start(self.url, self.member, self.filename)
        return True

    def actions(self, parent):
        add = QAction("レイヤをプロジェクトに追加", parent)
        add.triggered.connect(lambda: self.handleDoubleClick())
        return [add]


def remote_children(parent, node, url):
    result = []
    for child in node.children or []:
        path = f"{parent.path()}/{path_key(child.name)}"
        if child.kind == "folder" or zip_scanner.is_archive(child.name):
            result.append(KsjRemoteFolderItem(parent, child.name, path, child, url))
        else:
            result.append(KsjFileItem(parent, child.name, path, url, child.path))
    return result


class KsjRemoteFolderItem(QgsDataCollectionItem):
    def __init__(self, parent, name, path, node, url):
        super().__init__(parent, name, path)
        self.node, self.url = node, url
        self.setIcon(browser_icon("archive" if node.kind == "file" else "folder"))

    def createChildren(self):
        if self.node.kind == "file":
            return [
                message_item(
                    self,
                    "入れ子ZIPの一覧には本体取得が必要です。右クリックから配布ファイルを取得してください。",
                )
            ]
        return remote_children(self, self.node, self.url)

    def actions(self, parent):
        return link_actions(parent, [("配布ファイル全体をダウンロード", self.url)])
