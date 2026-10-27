"""README 用のスクリーンショットを QGIS 同梱 Python で描画して書き出す（macOS 専用）。

リポジトリのルートで実行する。

    source setup_qgis_env.sh
    .venv/bin/python scripts/capture_readme_images.py                     # 5 枚すべて
    .venv/bin/python scripts/capture_readme_images.py --only browser-loading-mode

- ウィンドウが数秒だけ画面に出る。システムがダーク表示でも Aqua（ライト）で描画する。
- browser-loading-indicator は ZIP の目次を部分取得するため通信が発生する。
- 利用者の QgsSettings には書き込まない。追加方法の表示は関数の差し替えで作る。
"""

import argparse
import ctypes
import ctypes.util
import sys
import time
from collections import namedtuple
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsBrowserModel,
    QgsBrowserProxyModel,
    QgsDataItem,
)
from qgis.gui import QgsBrowserTreeView
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QAbstractItemView, QApplication, QInputDialog

ROOT = Path(__file__).resolve().parents[1]
QGIS_PREFIX = "/Applications/QGIS.app/Contents/MacOS"
PROVIDER_NAME = "国土数値情報ブラウザ"
# 配布が 2 件（世界測地系・日本測地系）あり、選択ダイアログが開くメッシュ。
MESH_DATASET = "gml_datalist_KsjTmplt-L03-a-2021"
MESH_YEAR = "2021年"
MESH_CODE = "3622"
MESH_ARCHIVE = "L03-a-21_3622-jgd2011_GML.zip"
MESH_FILE = "L03-a-21_3622.shp"
SETTLE_SECONDS = 0.5
TIMEOUT_SECONDS = 60
# 読み込み中の判定は url と member だけを見る。
FakeKey = namedtuple("FakeKey", "url member")


def force_light_appearance():
    """システムがダーク表示でも Aqua（ライト）で描画する。QgsApplication 生成後に呼ぶ。"""
    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    appkit = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/AppKit.framework/AppKit"
    )
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]

    def send(receiver, selector, *args):
        objc.objc_msgSend.restype = ctypes.c_void_p
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [
            ctypes.c_void_p
        ] * len(args)
        return objc.objc_msgSend(
            receiver, objc.sel_registerName(selector.encode()), *args
        )

    aqua = ctypes.c_void_p.in_dll(appkit, "NSAppearanceNameAqua")
    appearance = send(objc.objc_getClass(b"NSAppearance"), "appearanceNamed:", aqua)
    nsapp = send(objc.objc_getClass(b"NSApplication"), "sharedApplication")
    send(nsapp, "setAppearance:", appearance)


def pump_until(app, predicate):
    """イベントを処理しながら条件が成り立つまで待つ。"""
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while not predicate():
        if time.monotonic() > deadline:
            raise TimeoutError("ブラウザ項目の読み込みが時間内に終わりませんでした")
        app.processEvents()
        time.sleep(0.01)


def settle(app):
    """描画が落ち着くまでイベントを回す。"""
    deadline = time.monotonic() + SETTLE_SECONDS
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def save_1x(pixmap, path):
    """Retina の 2x 画像を 1x に縮小して保存する。"""
    image = pixmap.toImage()
    ratio = pixmap.devicePixelRatio()
    if ratio > 1:
        image = image.scaled(
            int(image.width() / ratio),
            int(image.height() / ratio),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    if not image.save(str(path)):
        raise RuntimeError(f"保存できません: {path}")
    print(f"saved {path} {image.width()}x{image.height()}")


class Browser:
    """「国土数値情報」のルートだけを表示するブラウザツリー。"""

    def __init__(self, app):
        from ksj.browser import KsjDataItemProvider

        self.app = app
        self.provider = KsjDataItemProvider()
        QgsApplication.dataItemProviderRegistry().addProvider(self.provider)
        self.model = QgsBrowserModel()
        self.model.initialize()
        self.proxy = QgsBrowserProxyModel()
        self.proxy.setBrowserModel(self.model)
        self.proxy.setShownDataItemProviderKeyFilter([PROVIDER_NAME])
        # QGIS のブラウザパネルと同じく sortKey 順（分類・都道府県の公式順）に並べる。
        self.proxy.sort(0)
        self.view = QgsBrowserTreeView()
        self.view.setModel(self.proxy)
        self.view.setHeaderHidden(True)
        self.root = self.model.findPath("/ksj")

    def expand(self, index):
        """子を読み込んで展開し、子の index を返す。"""
        self.model.fetchMore(index)
        item = self.model.dataItem(index)
        pump_until(
            self.app,
            lambda: item.state() == QgsDataItem.State.Populated
            and self.model.rowCount(index) > 0,
        )
        self.view.expand(self.proxy.mapFromSource(index))
        rows = range(self.model.rowCount(index))
        return [self.model.index(row, 0, index) for row in rows]

    def child(self, index, name, exact=False):
        """index を展開し、name で始まる（exact なら一致する）子を返す。"""
        for child in self.expand(index):
            label = self.model.data(child)
            if (label == name) if exact else label.startswith(name):
                return child
        raise LookupError(f"ブラウザ項目が見つかりません: {name}")

    def select(self, index):
        self.view.setCurrentIndex(self.proxy.mapFromSource(index))

    def capture(self, width, height, path, focus=None):
        """表示して撮る。focus を渡すとその行が下端に来るまでスクロールする。"""
        self.view.resize(width, height)
        self.view.show()
        settle(self.app)
        if focus is not None:
            self.view.scrollTo(
                self.proxy.mapFromSource(focus),
                QAbstractItemView.ScrollHint.PositionAtBottom,
            )
            settle(self.app)
        save_1x(self.view.grab(), path)
        self.view.hide()

    def close(self):
        self.model.removeRootItems()
        QgsApplication.dataItemProviderRegistry().removeProvider(self.provider)


def capture_browser_panel(app, path):
    """分類 → データ → 年度 → 都道府県まで展開した全体像。"""
    browser = Browser(app)
    try:
        category = browser.child(browser.root, "地形（")
        dataset = browser.child(category, "低位地帯（ポリゴン）", exact=True)
        year = browser.child(dataset, "2015年")
        browser.expand(year)
        browser.select(dataset)
        browser.capture(440, 540, path)
    finally:
        browser.close()


def capture_loading_mode(app, path):
    """ルート直下の「追加方法」行と分類一覧。"""
    browser = Browser(app)
    try:
        browser.expand(browser.root)
        browser.capture(630, 390, path)
    finally:
        browser.close()


def capture_loading_indicator(app, path):
    """ZIP 内の .shp 行を読み込み中表示にした状態。"""
    from ksj import layer_loading

    browser = Browser(app)
    try:
        category = browser.child(browser.root, "土地利用（")
        dataset = browser.child(category, "土地利用3次メッシュ", exact=True)
        year = browser.child(dataset, MESH_YEAR)
        mesh = browser.child(year, MESH_CODE, exact=True)
        archive = browser.child(mesh, MESH_ARCHIVE)
        target = browser.child(archive, MESH_FILE, exact=True)
        item = browser.model.dataItem(target)
        key = FakeKey(item.url, item.member)
        layer_loading.pending[key] = None
        layer_loading.loading_signals.changed.emit()
        try:
            browser.select(target)
            browser.capture(900, 420, path, focus=target)
        finally:
            layer_loading.pending.pop(key, None)
            layer_loading.loading_signals.changed.emit()
    finally:
        browser.close()


def capture_loading_settings(app, path):
    """追加方法・保存先の設定ダイアログ。「一時レイヤー」が選ばれ、保存先は空欄。"""
    from ksj import local_storage

    dialog = local_storage.LoadingSettingsDialog()
    try:
        dialog.show()
        settle(app)
        save_1x(dialog.grab(), path)
    finally:
        dialog.close()


def capture_mesh_resource_dialog(app, path):
    """メッシュをクリックした後の配布ファイル選択ダイアログ。本来の関数で開く。"""
    from ksj import catalog, mesh_index

    dataset = catalog.load_dataset(MESH_DATASET)
    resources = [
        resource
        for resource in dataset["resources"]
        if resource["year"] == MESH_YEAR and catalog.mesh_code(resource) == MESH_CODE
    ]
    if len(resources) < 2:
        raise LookupError(f"メッシュ {MESH_CODE} に配布が 2 件以上ありません")
    state = {"saved": False}
    # モーダルが一度も現れないまま無期限に再予約すると、choose_resource の
    # exec() ループから抜けられず無言でハングする。期限を設けて必ず抜ける。
    deadline = time.monotonic() + TIMEOUT_SECONDS

    def shoot():
        dialog = QApplication.activeModalWidget()
        # 想定外のモーダル（エラー表示など）を撮らないよう、本物の選択ダイアログだけを待つ。
        if not isinstance(dialog, QInputDialog):
            if time.monotonic() > deadline:
                for widget in QApplication.topLevelWidgets():
                    widget.close()
                return
            QTimer.singleShot(100, shoot)
            return
        save_1x(dialog.grab(), path)
        state["saved"] = True
        dialog.reject()

    QTimer.singleShot(int(SETTLE_SECONDS * 1000), shoot)
    mesh_index.choose_resource(resources, MESH_CODE)
    if not state["saved"]:
        raise RuntimeError("配布ファイル選択ダイアログを取得できませんでした")


CAPTURES = {
    "browser-panel-light": capture_browser_panel,
    "browser-loading-mode": capture_loading_mode,
    "browser-loading-indicator": capture_loading_indicator,
    "loading-settings": capture_loading_settings,
    "mesh-resource-dialog": capture_mesh_resource_dialog,
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "imgs", help="出力先（既定: imgs/）"
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=sorted(CAPTURES),
        help="指定した画像だけを撮る（複数指定可）",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    QgsApplication.setPrefixPath(QGIS_PREFIX, True)
    app = QgsApplication([], True)
    app.initQgis()
    try:
        force_light_appearance()
    except (OSError, AttributeError, ValueError) as exc:
        print(f"Aqua に固定できませんでした。既定の外観で続けます: {exc}")

    from ksj import local_storage

    # 追加方法の表示を「一時レイヤー」に揃える。QgsSettings には書き込まない。
    local_storage.loading_mode = lambda: "temporary"
    local_storage.download_directory = lambda: ""

    args.output.mkdir(parents=True, exist_ok=True)
    try:
        for name in args.only or sorted(CAPTURES):
            CAPTURES[name](app, args.output / f"{name}.png")
    finally:
        app.exitQgis()


if __name__ == "__main__":
    main()
