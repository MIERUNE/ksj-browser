# README の再構成と画像の更新 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** README の画像 4 枚を現在のプラグインの表示に合わせて撮り直し、本文を見出しのある構成に組み直し、放置された画像を CI で検出できるようにする。

**Architecture:** 撮影は QGIS.app 同梱 Python でブラウザツリーとダイアログを描画して `grab()` するスクリプト `scripts/capture_readme_images.py` に集約する。README は設計書の構成どおりに全文を置き換える。`tests/test_readme_assets.py` が README の相対リンクの実在と `imgs/` の全ファイルの被参照を検査する。

**Tech Stack:** Python 3.9（QGIS.app 3.42 同梱）、PyQGIS（`QgsBrowserModel` / `QgsBrowserProxyModel` / `QgsBrowserTreeView`）、ctypes（macOS の外観固定）、pytest、ruff

**Spec:** `docs/superpowers/specs/2026-10-26-readme-restructure-design.md`

## Global Constraints

- 作業ブランチは `docs/readme-restructure`（設計書のコミット f20bfb4 が先頭にある）。
- Python 3.9 互換で書く（`match` 文、`X | Y` 型注釈、`str.removeprefix` は使わない）。型注釈は既存コードに合わせて付けない。
- ruff は `.venv/bin/ruff` を使う。`uv run` はロックファイルを書き換えるため使わない。
- テストは `source setup_qgis_env.sh` のうえで `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest …` で実行する。
- 撮影スクリプトは利用者の QgsSettings に書き込まない。追加方法の表示は `ksj.local_storage.loading_mode` / `download_directory` の差し替えで作る。
- 撮影はライト表示（Aqua）、Retina を 1x に縮小した PNG。
- README の文体はです・ます調。英数字と日本語の間は空白あり（「QGIS の」「Shapefile は」）。全角「／」「・」は従来どおり、半角スラッシュは ID・拡張子のみ。
- コード内コメント、コミットメッセージ、PR 本文は日本語。コミットは Conventional Commits（`docs:` / `feat:` / `test:`）。
- コミットメッセージ末尾に次の 2 行を付ける。

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
```

---

## ファイル構成

| パス | 役割 | 操作 |
| --- | --- | --- |
| `scripts/capture_readme_images.py` | README 用スクリーンショット 4 枚の生成（macOS 専用） | 新規 |
| `imgs/browser-panel-light.png` | ブラウザ全体（地形 → 低位地帯 → 2015年 → 都道府県） | 置換 |
| `imgs/browser-loading-mode.png` | ルートと「追加方法」行と分類一覧 | 置換 |
| `imgs/browser-loading-indicator.png` | ZIP 内の `.shp` 行の読み込み中表示 | 置換 |
| `imgs/mesh-resource-dialog.png` | メッシュの配布ファイル選択ダイアログ | 新規（`.jpg` を置き換え） |
| `README.md` | 設計書の構成で全文を置き換え | 置換 |
| `tests/test_readme_assets.py` | README の相対リンクと `imgs/` の被参照を検査 | 新規 |
| `imgs/browser-panel-dark.png`、`imgs/browser-file-context-menu.png`、`imgs/browser-mesh-index-action-dark.png`、`imgs/mesh-index-qgis.jpg`、`imgs/mesh-resource-dialog.jpg`、`imgs/processing-load-encoding.png` | 未参照になる画像 | 削除 |

事前に確認済みの事実（オフスクリーンで実測）:

- `QgsBrowserProxyModel.setShownDataItemProviderKeyFilter(["国土数値情報ブラウザ"])` でプロキシの最上位行は「国土数値情報」1 行になる。
- 同梱カタログの `gml_datalist_KsjTmplt-L03-a-2021`（土地利用3次メッシュ）の 2021年・メッシュ 3622 には配布が 2 件（`L03-a-21_3622-jgd2011_GML.zip ｜ 世界測地系 ｜ 0.03MB`、`L03-a-21_3622-tky_GML.zip ｜ 日本測地系 ｜ 0.03MB`）あり、`choose_resource` はダイアログ（`QInputDialog`、題名「メッシュ 3622 のデータ」）を開く。
- `L03-a-21_3622-jgd2011_GML.zip` を展開すると `L03-a-21_3622.geojson`、`L03-a-21_3622.shp`、`L03-a-21_3622.xml` の 3 行が出る（通信あり、約 4 秒）。
- `ksj.layer_loading.pending` に `url`・`member` 属性を持つキーを入れて `loading_signals.changed.emit()` すると、該当 `KsjFileItem.name()` が「読み込み中… L03-a-21_3622.shp」になる。キーを消して再度 emit すると戻る。
- ctypes で `NSApplication.sharedApplication` に `NSAppearanceNameAqua` を `setAppearance:` すると `effectiveAppearance` が Aqua になる。

---

### Task 1: 撮影スクリプトと画像 4 枚

**Files:**
- Create: `scripts/capture_readme_images.py`
- Replace: `imgs/browser-panel-light.png`、`imgs/browser-loading-mode.png`、`imgs/browser-loading-indicator.png`
- Create: `imgs/mesh-resource-dialog.png`

**Interfaces:**
- Consumes: `ksj.browser.KsjDataItemProvider`、`ksj.local_storage.loading_mode` / `download_directory`、`ksj.layer_loading.pending` / `loading_signals`、`ksj.catalog.load_dataset` / `mesh_code`、`ksj.mesh_index.choose_resource`
- Produces: `imgs/` の PNG 4 枚。Task 2 の README がこのファイル名を参照する。

- [ ] **Step 1: スクリプトを作成する**

`scripts/capture_readme_images.py` を次の内容で作成する。

```python
"""README 用のスクリーンショットを QGIS 同梱 Python で描画して書き出す（macOS 専用）。

リポジトリのルートで実行する。

    source setup_qgis_env.sh
    .venv/bin/python scripts/capture_readme_images.py                     # 4 枚すべて
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
from qgis.PyQt.QtWidgets import QAbstractItemView, QApplication

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

    def shoot():
        dialog = QApplication.activeModalWidget()
        if dialog is None:
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
```

- [ ] **Step 2: lint とフォーマットを確認する**

Run:

```bash
.venv/bin/ruff check scripts/capture_readme_images.py
.venv/bin/ruff format --check scripts/capture_readme_images.py
```

Expected: `All checks passed!` と `1 file already formatted`。フォーマット差分が出たら `.venv/bin/ruff format scripts/capture_readme_images.py` で直す。

- [ ] **Step 3: 4 枚を生成する**

Run:

```bash
source setup_qgis_env.sh
.venv/bin/python scripts/capture_readme_images.py
```

Expected: 標準出力に `saved …/imgs/browser-loading-indicator.png 900x420` など 4 行。ウィンドウが数秒出て閉じる。`PROJ: proj_create_from_database` の警告は無視してよい。「Aqua に固定できませんでした」が出た場合は画像がダーク表示になっているので、原因を直してから撮り直す。

- [ ] **Step 4: 画像を目視で確認する**

Read ツールで `imgs/browser-panel-light.png`、`imgs/browser-loading-mode.png`、`imgs/browser-loading-indicator.png`、`imgs/mesh-resource-dialog.png` を開き、次を確認する。

- 4 枚ともライト表示（白地）。
- ブラウザの 3 枚: ルートが「国土数値情報」で、左のアイコンが `ksj/icons/plugin.png`（濃いティール地のタイル）。直下に「追加方法: 一時レイヤー（フォルダに保存しない）」の行がある。
- `browser-panel-light.png`: 「地形（5項目）」の下に「低位地帯（ポリゴン）」が選択状態で、「2015年」の下に都道府県が並ぶ。
- `browser-loading-indicator.png`: 「L03-a-21_3622-jgd2011_GML.zip ｜ 世界測地系 ｜ 0.03MB」の下に「読み込み中… L03-a-21_3622.shp」の行が選択状態で、左のアイコンが回転アイコン。
- `mesh-resource-dialog.png`: 題名「メッシュ 3622 のデータ」、「追加する配布ファイルを選択」、プルダウンに「1. L03-a-21_3622-jgd2011_GML.zip ｜ 世界測地系 ｜ 0.03MB」。

Run:

```bash
sips -g pixelWidth -g pixelHeight imgs/browser-panel-light.png imgs/browser-loading-mode.png imgs/browser-loading-indicator.png imgs/mesh-resource-dialog.png
```

Expected: それぞれ 440×540、630×390、900×420、ダイアログは幅 500〜600 程度・高さ 100〜150 程度（2x のままなら倍の値になるので、その場合は `save_1x` の縮小が効いていない）。

表示が期待と違う場合（ルートが複数ある、追加方法の行がない、読み込み中にならない）はスクリプトを直して該当画像だけ `--only` で撮り直す。

- [ ] **Step 5: コミットする**

```bash
git add scripts/capture_readme_images.py imgs/browser-panel-light.png imgs/browser-loading-mode.png imgs/browser-loading-indicator.png imgs/mesh-resource-dialog.png
git commit -q -F - <<'EOF'
docs: README 用の画像を撮影スクリプトで現在の表示に更新

ブラウザパネルの 3 枚はルート名・ルートアイコン・「追加方法」行を現行に合わせ、
配布ファイル選択ダイアログはライト表示の PNG で撮り直した。
撮影手順を scripts/capture_readme_images.py に残す。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
EOF
```

---

### Task 2: README の全文置き換え

**Files:**
- Replace: `README.md`

**Interfaces:**
- Consumes: Task 1 の画像ファイル名（`imgs/browser-panel-light.png`、`imgs/browser-loading-mode.png`、`imgs/browser-loading-indicator.png`、`imgs/mesh-resource-dialog.png`）と既存の `imgs/browser-file-icons.png`、`imgs/loading-settings.png`、`imgs/browser-mesh-index-action-light.png`、`imgs/mesh-layer-selection.png`。
- Produces: Task 3 のテストが検査する README。参照する画像は上の 8 枚、相対リンクは `ksj/catalog/index.json`、`specs/005-mesh-index/verification.md`、`specs/004-complete-catalog/verification.md`、`requirements-test.txt`、`metadata.txt`。

- [ ] **Step 1: README.md を次の内容で置き換える**

Write ツールで `README.md` 全体を次の内容にする（先頭の `# ` から末尾まで）。

````markdown
# ksj-browser — 国土数値情報ブラウザ（QGIS プラグイン）

[国土数値情報の公式サイト](https://nlftp.mlit.go.jp/ksj/)の現行形式・過年度版・旧形式を、QGIS のブラウザパネルから探して地図に追加できます。公式一覧の分類と配布ファイルの情報を同梱しているため、起動時に全データをダウンロードする必要はありません。データ本体は、レイヤーを追加するときに必要なファイルだけを取得します。

Processing ツールボックスにも、検索・取得・読み込みのアルゴリズム（プロバイダ `ksj`）があります。一覧は「[Processing アルゴリズム](#processing-アルゴリズム)」を参照してください。

QGIS 3.44 以上 4.x まで（Qt 5・Qt 6 の両方）に対応します。

![QGIS のブラウザパネルで国土数値情報を分類・データ・年度・地域の順に展開した表示](imgs/browser-panel-light.png)

## ブラウザパネルで使う

### データを探す

1. QGIS のブラウザパネルで「国土数値情報」を展開します。
2. 水域・土地利用・災害／防災・施設・交通などの分類からデータを選びます。
3. 年度（新しい順）、地域・メッシュ、市区町村（該当データのみ）を選びます。
4. 形式・河川名・測地系・容量を確認して ZIP を展開します。この段階では ZIP の目次だけを部分取得し、データ本体を保存・解凍しません。

全国一括・都道府県別・メッシュ別・河川別の配布を保持し、同じ地域の SHP／GML／GeoJSON や異なる測地系を省略しません。都市計画決定情報は都道府県 → 市区町村の順に選択できます。

フォルダは分類、積層アイコンはデータ、カレンダーは年度、ピンは地域、ZIP アイコンは圧縮された配布ファイルを示します。ZIP 内のファイルは、ベクタ・文書・圧縮ファイル・表・ラスタの種類ごとに異なるアイコンで示します。分類には項目数を表示し、データ・年度・地域の配布ファイル数はマウスを重ねると確認できます。

![ZIP 内のファイル種別ごとのアイコン（明るい背景と暗い背景）](imgs/browser-file-icons.png)

データセットを右クリックすると、公式の説明・属性定義・利用条件を開けます。配布ファイルを右クリックすると、その版の説明ページまたは原本ダウンロードを開けます。最新版と旧版で利用条件が異なる場合があるため、使用する版の条件を確認してください。

旧形式は「JPGIS1.0（XML）」「旧統一フォーマット（シェープ・XML）」「旧統一フォーマット（TXT・CSV）」にまとめています。Shapefile、GeoJSON、GDAL 対応の GML/XML、GeoPackage、CSV、ラスタなどは QGIS で開けます。独自仕様の旧 XML・TXT や LZH など、GDAL で直接読めない形式は原本をダウンロードして利用します。入れ子 ZIP を含む配布全体の取得・展開には、Processing の取得アルゴリズムも使えます。

### レイヤーを追加する

ファイルをダブルクリック、またはマップへドラッグすると、必要なファイルを取得して追加します。初回に追加方法が未設定の場合は、ここで設定します。GML・GeoPackage など複数レイヤーを含むファイルは、追加時にサブレイヤーを調べてまとめて追加します。

取得・追加の処理中は、対象ファイルの行に回転アイコンと「読み込み中…」を表示します。完了・失敗・キャンセル時は元の表示に戻ります。右クリックから追加した場合も同じ表示になります。進捗の確認・取消は QGIS のタスクから行えます。

![対象ファイルの行に読み込み中と回転アイコンを表示](imgs/browser-loading-indicator.png)

ZIP・フォルダの閲覧には保存先の設定が不要です。ZIP の目次取得には少量の通信が発生します。Shapefile は同じフォルダ・同じ名前の `.shp`・`.shx`・`.dbf` と、存在する `.prj`・`.cpg` などを一組として取得します。別のレイヤーや配布全体をまとめて取得しません。GML のスキーマ、CSV・ラスタの付属ファイルも対象形式に応じて取得します。

配布元が HTTP の部分取得に対応しない場合や、圧縮された入れ子 ZIP の内部を閲覧する場合は、自動で全体取得せず案内を表示します。必要なら右クリックの「配布ファイルをダウンロード」から全体を取得してください。外部データを参照する VRT も全体取得が必要です。

### 追加方法・保存先を設定する

ブラウザの「国土数値情報」の先頭にある「追加方法」の項目に、現在の追加方法・保存先を表示します。この項目をダブルクリックするか、「国土数値情報」または配布ファイルの右クリックから「追加方法・保存先を設定…」を選ぶと、設定画面が開きます。一度設定すると、別のプロジェクトでも同じ方法を使います。

![ブラウザ先頭に現在の追加方法を表示](imgs/browser-loading-mode.png)

設定画面では、次のいずれかを選びます。

- **フォルダに保存して追加**: 取得したファイルを指定フォルダに保存し、次回から再利用します。
- **一時レイヤーとして追加**: 取得したファイルを一時フォルダに置き、レイヤーを閉じると削除します。
- **クラウド（kumoy）にアップロードして追加**: 取得したファイルを [kumoy](https://www.kumoy.io/) に送り、クラウド上のレイヤーを地図に追加します。

![保存・一時レイヤー・kumoy を切り替える設定画面](imgs/loading-settings.png)

設定変更は、すでにブラウザに表示されている項目にも、次回の追加時から反映されます。既存レイヤーや保存済みファイルは移動しません。設定を取り消した場合は元の状態を保ちます。この設定は、ブラウザのファイル項目とメッシュ索引からの追加に適用します。Processing の取得アルゴリズムは、設定にかかわらず指定フォルダに配布全体を保存します。

保存先に取得済みのデータがあれば、いずれの方式でも通信せず再利用します。

#### フォルダに保存して追加

選択したレイヤーに必要なファイルを保存先フォルダに保存します。次回からは保存済みデータを再利用し、プロジェクトを開き直しても通常ファイルを参照します。保存先の構成、公開元が更新されたときの取り直し、プロジェクト共有時の注意は「[保存したデータの扱い](#保存したデータの扱い)」を参照してください。

#### 一時レイヤーとして追加

ベクタ・ラスタとも取得したファイルを一時フォルダに置き、そのまま参照します。保存先フォルダの指定は不要です。同じファイルから追加したレイヤーをすべて閉じると一時フォルダを削除します。QGIS の「レイヤーを複製」で作った複製は数に入らないため、元のレイヤーをすべて閉じると複製は表示できなくなります。

**プロジェクト保存だけでは一時データは残りません。** 残したいレイヤーは別途ファイルへ保存してください。メッシュ索引から追加する場合は配布ファイル全体を一時フォルダへ取得します。

#### クラウド（kumoy）にアップロードして追加

[kumoy](https://www.kumoy.io/) は地図データをクラウドで共有・公開できるサービスです。この追加方法には kumoy の QGIS プラグイン（QGIS 3.44 以上）が必要です。未インストールの場合は設定画面でインストールを、無効の場合は有効化を案内します。アップロード前に、kumoy ブラウザパネルの Kumoy 項目からログインしてください。

ファイルをダブルクリックすると、必要なファイルを一時フォルダへ取得し、kumoy へアップロードします。Shapefile は文字コードの確認画面が開き、自動判定を初期値に、先頭 5 地物の文字列属性を見ながら UTF-8 / Shift_JIS / EUC-JP を選べます。GeoJSON・GML・GeoPackage は UTF-8 固定のため確認しません。座標系が未定義のデータは、配布元の説明を確認して元データの座標系を選びます。座標値や保存済みファイルは変更せず、アップロードするレイヤーに設定します。キャンセルしたレイヤーは送りません。続いて kumoy のアップロード画面で送り先のプロジェクトとレイヤー名を選びます。ジオメトリや件数などの制約は kumoy の画面で確認できます。

完了後は kumoy のレイヤーを地図へ追加し、一時フォルダを削除するため、ローカルにファイルを残しません。保存済みデータを再利用した場合、その保存データは保持します。kumoy ブラウザで選択中と異なるプロジェクトへ送った場合は、プロジェクトを切り替えてから追加してください。メッシュ索引からの追加も同じ流れです。

### 地図のメッシュをクリックして追加する

道路などメッシュ番号で配布されるデータは、番号を調べずに地図から選べます。

1. ブラウザでデータの**年度**を展開し、先頭の格子と「＋」のアイコンが付いた**「メッシュ索引を地図に追加」**をダブルクリックします。年度の右クリックメニューからも実行できます。

   ![年度の下に表示される「メッシュ索引を地図に追加」の項目](imgs/browser-mesh-index-action-light.png)

2. 配布があるメッシュの枠と番号が表示され、地物アクションのツールに切り替わります。背景地図と重ね、必要な場所へ移動・拡大してください。
3. メッシュ内をクリックします。複数の配布がある場合は、形式・測地系・容量などを確認してファイルを選びます。1 件だけの場合は配布ファイルの選択を省略します。追加方法・保存先の設定に従います。「フォルダに保存して追加」で保存先が未設定なら、このとき一度だけフォルダを選びます。

   ![メッシュをクリックした後に配布ファイルを選ぶ画面](imgs/mesh-resource-dialog.png)

4. 配布ファイル内に複数のレイヤーがある場合は、追加したいレイヤーにチェックを入れ、**「選択したレイヤーを追加」**を押します。複数選択できます。レイヤー名と拡張子付きのファイル名を確認し、同じ内容の SHP／GeoJSON などから必要なものだけを選んでください。レイヤーが 1 つだけの場合はそのまま追加します。

   ![配布ファイル内のレイヤーを複数選択する画面](imgs/mesh-layer-selection.png)

5. 索引を選択したまま、続けて別のメッシュをクリックできます。「フォルダに保存して追加」では、同じ配布ファイルを再度選ぶと、まだ追加していないレイヤーを選択できます。「一時レイヤーとして追加」と「クラウド（kumoy）にアップロードして追加」では毎回すべてのレイヤーを候補に出します。

移動・拡大などでツールを切り替えた後は、索引レイヤーを選び、QGIS の**「地物アクションの実行」**に戻してください。「地物情報を表示」の結果や属性テーブルの地物アクションからも「このメッシュのデータを追加」を実行できます。

この操作は KSJ プラグインが提供するため、QGIS 4 の埋め込みスクリプトの信頼確認は不要です。プロジェクトを保存していなくても利用できます。

索引の作成はオフラインで行い、未取得データのダウンロードはクリック後に開始します。保存済みなら通信せず読み込みます。取得の進捗確認・中止は QGIS のタスクから行えます。読み込み中の同じ配布への連打を防ぎます。「フォルダに保存して追加」では追加済みレイヤーの重複も防ぎ、削除したレイヤーは再度クリックして追加できます。取得失敗はメッセージバーに表示され、同じ操作で再試行できます。

索引はプロジェクトに保存されます。再度開いて使用する際も KSJ プラグインを有効にしてください。対象は同梱カタログの配布単位である **1 次メッシュ（4 桁、約 80 km）** です。1 km・500 m などのデータでも、索引は配布ファイルの単位を示します。世界測地系で位置を示す案内用の枠であり、旧日本測地系のデータの厳密な境界には使えません。

実装と動作確認の詳細は[メッシュ索引の検証記録](specs/005-mesh-index/verification.md)を参照してください。

## 保存したデータの扱い

### 保存先の構成

保存データは配布ファイル名と識別子のフォルダ直下に、ZIP 内のフォルダ構造を保って配置します。同じ ZIP から別のレイヤーを追加すると、同じ配布フォルダにファイルを追加します。全体取得も同じ保存先を使います。同名の別配布は外側の識別子で区別します。取得状態・目次・作業ファイルは隠しフォルダ `.ksj` に分け、失敗・取消時には今回追加した途中データを削除します。

### 公開元が更新されたとき

保存したデータは自動更新・自動削除しません。公開元が同じ URL のファイルを更新し、取り直す必要がある場合は、使用中のレイヤーを閉じ、保存先から対象配布のサブフォルダ（配布ファイル名で始まるフォルダ）を削除した後に再読み込みしてください。利用中のデータを削除・移動すると、保存したプロジェクトからも参照できなくなります。

### プロジェクトを共有する

**プロジェクトを共有するときは、参照する保存データも一緒に共有してください。** 受け手が参照できる共有フォルダを使うか、プロジェクトとデータの配置を保って渡します。

QGIS のプロジェクト設定でパスを「相対」にすると、プロジェクトと保存したデータの配置を保ったまま移動できます。入れ子 ZIP から展開したファイルも同様です。Shapefile などは必要な付属ファイルを含め、配布単位のフォルダごと共有してください。

## 文字コード

Shapefile の文字コードは、取得したファイルの属性値と `.cpg`・言語 ID・フォルダ名から自動判定して適用します。レイヤーの文字コード設定を変更した場合はメッセージログ（タグ `KSJ`）で確認できます。判定できない場合は QGIS の既定に従うため、文字化けしたときはレイヤープロパティで文字コードを変更してください。

UTF-8 と cp932 の両方で復号できる値（一部の半角カナなど）は UTF-8 を優先するため、誤判定する場合があります。その場合もレイヤープロパティ、または Processing の読み込みアルゴリズムの文字コード指定で変更してください。Shift_JIS は拡張漢字や丸数字を保持するため CP932 として読み込みます。GeoJSON・GML・GeoPackage は UTF-8 固定です。

## 収録範囲とカタログの更新

カタログの取得日、一覧項目数、ページ数、重複を除いた配布ファイル数、取得エラーは [`ksj/catalog/index.json`](ksj/catalog/index.json) に記録しています。分類を展開するだけでは通信せず、データセット定義は選択時に読み込みます。ZIP の展開時にはファイル名を列挙するための目次を部分取得し、レイヤー追加時に必要なデータを取得します。公式サイトの配布状態や回線により、取得できない場合はブラウザにエラーを表示します。

収録範囲の照合・代表データの読み込み・テスト結果は[検証記録](specs/004-complete-catalog/verification.md)を参照してください。

更新には Python 3.9 以上と curl を使用します。全配布 ZIP のミラーは作成せず、公開 HTML と都市計画の配布一覧だけを収集します。

```bash
python3 scripts/update_catalog.py --refresh
```

- 現行一覧と 3 種類の旧形式一覧から、関連する詳細ページ・旧版を辿ります。
- 公開された正確な URL、年度、地域、市区町村、形式、測地系、容量、説明ページを保持します。
- HTML の結合セル、和暦、相対 URL、JavaScript の配布一覧に対応します。
- 巡回と解析は逐次実行し、通信は既定で 1 秒の間隔を空けます。`--request-delay` で調整できます。`--workers` は廃止しました。
- HTML キャッシュは `.cache/ksj-catalog/` に保存します。`--refresh` を省略すると再利用します。
- 取得失敗時は通常の更新を中止し、既存カタログを上書きしません。画像認証を通常のデータページとして登録しません。
- 索引を含む全 JSON の書き込みが成功した後、出力先直下の不要な JSON を削除します。`--output` にはカタログ専用のディレクトリを指定してください。通常更新の取得失敗・書き込み失敗時にはこの削除を行いません。
- 画像認証が出た場合は利用者がブラウザで認証を完了した後、`--retry-failed` で認証画面のキャッシュを再取得できます。
- `--allow-incomplete` は調査用です。失敗を明示した未完了カタログを出力するため、通常の更新には使用しません。

更新処理は `scripts/update_catalog.py` に統一しています。

## Processing アルゴリズム

プラグインを有効化すると、Processing ツールボックスの「国土数値情報」に次の 4 つのアルゴリズムが表示されます。プラグインを更新した後は再読み込みしてください。ダイアログでは表示名から選べ、Python・バッチ・モデルビルダーでは ID と値を指定します。

| アルゴリズム ID | 主な入力 | 出力 |
| --- | --- | --- |
| `ksj:search_datasets` | `QUERY`、`CATEGORY`、`EDITION` | 検索結果の `RESULTS` JSON、総件数 `TOTAL` |
| `ksj:list_resources` | `DATASET_ID`、`YEAR`、`REGION`、`FORMAT`、`QUERY` | 配布一覧の `RESULTS` JSON、総件数 `TOTAL` |
| `ksj:download_resource` | `DATASET_ID`、`RESOURCE_ID`、`DIRECTORY` | `LOCAL_PATH`、取得元・レイヤー一覧の `RESULTS` JSON |
| `ksj:load_layer` | `SOURCE`、`PROVIDER`（`ogr` / `gdal`）、任意の `NAME`、`ENCODING`（0: 自動判定、1: UTF-8、2: Shift_JIS、3: EUC-JP） | 単一レイヤー `OUTPUT` |

入出力の詳細とページ指定（`LIMIT`・`OFFSET`）は、`processing.algorithmHelp("ksj:search_datasets")` のように確認できます。

## 開発環境

### Docker でテスト（推奨）

Docker が動作する環境で、リポジトリのルートから次を実行します。ホスト側に QGIS や Python のテスト依存をインストールする必要はありません。

```bash
bash scripts/test-docker.sh
```

公式の `qgis/qgis:3.44` イメージ内で、QGIS のシステムパッケージを共有する一時仮想環境に [`requirements-test.txt`](requirements-test.txt) のテスト依存（`pytest`・`pytest-qgis`・`pytest-cov`、バージョン固定）をインストールし、Xvfb 上で全テストと `ksj`・`scripts` のカバレッジを実行します。カバレッジは端末に表示するほか `coverage.xml` に書き出します。初回はイメージ取得、各実行時はテスト依存の取得にネットワーク接続が必要ですが、pip のキャッシュを Docker ボリューム `ksj-test-pip-cache` に残すため 2 回目以降のダウンロードは省略されます。終了後にコンテナと仮想環境は削除されます。

QGIS のバージョンや pytest の引数を指定できます。引数を渡した場合は既定の `-v` とカバレッジ引数を置き換えます。

```bash
QGIS_TEST_IMAGE=qgis/qgis:4.0-trixie bash scripts/test-docker.sh
QGIS_TEST_IMAGE=qgis/qgis:4.2-trixie bash scripts/test-docker.sh
bash scripts/test-docker.sh tests/test_catalog.py -q
```

公式イメージに合わせて既定では `linux/amd64` を使います。Apple Silicon では Docker Desktop の AMD64 エミュレーションを有効にしてください。プラットフォームは `DOCKER_DEFAULT_PLATFORM` で変更できます。

GitHub Actions でも同じスクリプトを使い、QGIS 3.44（最低対応版）・4.0・4.2 のテストとカバレッジを実行し、各バージョンの `coverage.xml` を成果物として保存します。別のジョブで Ruff の lint・format と、公式の pyqgis4-checker による Qt6 互換チェックを確認します。Pull Request、`main` への push、Actions 画面からの手動実行に対応しています。Actions のバージョン更新は Dependabot が月次で提案します。

### ローカルで lint

```bash
uv sync --locked
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```

### Qt6 互換チェック

公式の [pyqgis4-checker](https://github.com/qgis/pyqgis4-checker) で、PyQt6 / QGIS 4 で動かない書き方（修飾のない enum など）を検出します。CI の Lint ワークフローと同じイメージ・同じスクリプトです。

```bash
docker run --rm --pull always --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --workdir /workspace/ -v "$(pwd):/workspace/" \
  ghcr.io/qgis/pyqgis4-checker:main-ubuntu \
  pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log .
```

指摘は `pyqt6_checker.log`（`.gitignore` 済み）に書き出されます。`--dry_run` を外すとファイルを直接書き換えるので、コミット済みの状態で実行して差分を確認してください。イメージのタグ `main-ubuntu` は QGIS の更新に追従する移動タグで、Dependabot の管理対象外です。

### QGIS をインストールした環境でテスト

プラグインの対応 QGIS バージョン（`qgisMinimumVersion`・`qgisMaximumVersion`）は [`metadata.txt`](metadata.txt) を参照してください。QGIS 付属 Python とシステムサイトパッケージを共有し、別の PyQt をインストールしないでください。

```bash
uv venv --python /Applications/QGIS.app/Contents/MacOS/bin/python3 --system-site-packages
source setup_qgis_env.sh
uv pip install --python .venv/bin/python -r requirements-test.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest --cov=ksj --cov=scripts --cov-report=term-missing
uv run ruff check .
```

Windows では、QGIS をインストールした環境の **OSGeo4W Shell** を開き、QGIS 付属 Python を指定して仮想環境を作成します。以下は `C:\OSGeo4W` に QGIS を入れた例です。スタンドアロン版や LTR では、インストール先と `apps\qgis` の部分を実際のパス（例: `apps\qgis-ltr`）に置き換えてください。

```bat
cd C:\path\to\ksj-browser
set "QGIS_PREFIX_PATH=C:\OSGeo4W\apps\qgis"
set "PYTHONPATH=%QGIS_PREFIX_PATH%\python;%PYTHONPATH%"
set "PATH=%QGIS_PREFIX_PATH%\bin;%PATH%"
python -c "import sys; print(sys.executable)"
uv venv --python "C:\OSGeo4W\bin\python3.exe" --system-site-packages
.venv\Scripts\python.exe -c "from qgis.core import Qgis; print(Qgis.QGIS_VERSION)"
uv pip install --python .venv\Scripts\python.exe -r requirements-test.txt
.venv\Scripts\python.exe -m pytest -q
```

`uv venv --python` には、直前のコマンドで確認した QGIS 付属 Python の実際のパスを指定します。QGIS のモジュールと DLL の探索には環境変数が必要です（[QGIS 公式開発ガイド](https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/intro.html#running-custom-applications)）。Windows の手順は実機で未検証です。

VS Code では Python 拡張機能を有効にし、コマンドパレットの **Python: Select Interpreter** → **Enter interpreter path** から、Windows は `.venv\Scripts\python.exe`、macOS は `.venv/bin/python` を選択します。Windows では環境設定済みの OSGeo4W Shell から `code .` で起動し、統合ターミナルでも `from qgis.core import Qgis` のインポートが通ることを確認してください。既存の VS Code プロセスが環境を引き継がない場合は、すべてのウィンドウを終了してから起動し直します。

標準ライブラリだけを使う解析・分類テストは、QGIS なしでも実行できます。

```bash
python3 -m unittest tests.test_update_catalog tests.test_catalog
```

macOS で QGIS 付属 Python をターミナルから実行し、GDAL が `unable to get local issuer certificate` を返す場合は、OS 標準 CA ファイルの存在を確認して `CURL_CA_BUNDLE=/etc/ssl/cert.pem` を実行時に指定します。証明書検証を無効化する必要はありません。

## 構成

| パス | 役割 |
| --- | --- |
| `ksj/catalog/index.json` | 分類・データセット索引・収集結果 |
| `ksj/catalog/*.json` | データセットごとの配布ファイル定義 |
| `ksj/catalog.py` | 遅延読み込み・年度や地域の分類 |
| `ksj/catalog_fields.py` | 収集と表示で共有する公式配布表の列名定義 |
| `ksj/catalog_browser.py` | 分類・配布ファイル・ZIP 内のファイル・設定表示のブラウザ項目 |
| `ksj/remote_zip.py` | ZIP の目次と選択したレイヤー一式の部分取得 |
| `ksj/layer_loading.py` | 保存／一時レイヤー／kumoy の非同期追加・取消・ドラッグ対応 |
| `ksj/encoding_check.py` | Shapefile の文字コード判定・適用とアップロード前の確認 |
| `ksj/kumoy_upload.py` | kumoy プラグインの確認・インストール支援・アップロード |
| `ksj/temporary_files.py` | 一時レイヤー用ディレクトリの作成と削除 |
| `ksj/messages.py` | メッセージログ・メッセージバーへの通知 |
| `ksj/mesh_index.py` | 配布メッシュ索引・地物アクション・非同期読み込み |
| `ksj/processing_provider.py` | Processing プロバイダの登録・アルゴリズム一覧 |
| `ksj/processing_widgets.py` | Processing の選択式入力画面 |
| `ksj/processing_algorithms.py` | 検索・配布一覧・取得・解析用レイヤー出力 |
| `ksj/browser.py` | QGIS プロバイダ・ルート項目 |
| `ksj/local_storage.py` | 保存先設定・データの取得と解凍・再利用 |
| `ksj/zip_scanner.py` | ローカルフォルダ・ZIP の探索とレイヤー候補の分類 |
| `scripts/update_catalog.py` | 公式カタログ生成 |
| `scripts/capture_readme_images.py` | README 用スクリーンショットの生成（macOS） |
| `tests/` | HTML 解析・分類・実 QGIS での回帰テスト |
| `specs/004-complete-catalog/` | 全データ対応の計画と検証記録 |

パッケージ内部では相対インポートを使用し、Plugin Reloader との互換性を保ちます。

## ライセンス

プラグインは MIT ライセンスです。国土数値情報のデータは各版の使用許諾条件に従ってください。
````

- [ ] **Step 2: 見出しと画像の位置を確認する**

Run:

```bash
grep -n "^#" README.md
grep -n "imgs/" README.md
```

Expected: 見出しが設計書の順（`# ksj-browser`、`## ブラウザパネルで使う`、`### データを探す`、`### レイヤーを追加する`、`### 追加方法・保存先を設定する`、`#### フォルダに保存して追加`、`#### 一時レイヤーとして追加`、`#### クラウド（kumoy）にアップロードして追加`、`### 地図のメッシュをクリックして追加する`、`## 保存したデータの扱い`、`### 保存先の構成`、`### 公開元が更新されたとき`、`### プロジェクトを共有する`、`## 文字コード`、`## 収録範囲とカタログの更新`、`## Processing アルゴリズム`、`## 開発環境`、`### Docker でテスト（推奨）`、`### ローカルで lint`、`### Qt6 互換チェック`、`### QGIS をインストールした環境でテスト`、`## 構成`、`## ライセンス`）。画像参照は 8 件（`browser-panel-light`、`browser-file-icons`、`browser-loading-indicator`、`browser-loading-mode`、`loading-settings`、`browser-mesh-index-action-light`、`mesh-resource-dialog.png`、`mesh-layer-selection`）。

- [ ] **Step 3: 旧表記が残っていないことを確認する**

Run:

```bash
git grep -n "（KSJ）" -- README.md imgs
grep -n "QGISの\|QGISを\|QGISで\|Shapefileは\|Processingの\|Processingツール" README.md
```

Expected: どちらも出力なし。

- [ ] **Step 4: コミットする**

```bash
git add README.md
git commit -q -F - <<'EOF'
docs: README を操作の流れ順に再構成する

「使い方」に混在していた探し方・追加・設定・保存データ・文字コードを
見出しで分け、ブラウザと Processing の両方に関わる節を独立させた。
Processing の手順と Python の例は削り、アルゴリズム ID の表だけを残す。
メッシュ索引の節に既存の画像 3 枚を載せ、英数字と日本語の間の空白を統一した。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
EOF
```

---

### Task 3: 画像の整合テストと不要画像の削除

**Files:**
- Create: `tests/test_readme_assets.py`
- Delete: `imgs/browser-panel-dark.png`、`imgs/browser-file-context-menu.png`、`imgs/browser-mesh-index-action-dark.png`、`imgs/mesh-index-qgis.jpg`、`imgs/mesh-resource-dialog.jpg`、`imgs/processing-load-encoding.png`

**Interfaces:**
- Consumes: Task 2 の README、`specs/**/*.md` の相対リンク、`imgs/` のファイル一覧。
- Produces: CI で動く 2 テスト。`relative_targets(markdown_path) -> list[str]` はこのテスト内だけで使う。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_readme_assets.py` を次の内容で作成する。

```python
"""README と imgs/ の整合。相対リンクが実在し、画像が放置されていないこと。"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
IMAGES = ROOT / "imgs"
# Markdown の `](target)` を拾う。空白や `)` を含むパスは使っていない。
LINK = re.compile(r"\]\(([^)\s]+)\)")


def relative_targets(markdown):
    """Markdown 内の相対リンク先。URL とページ内リンクは除く。"""
    return [
        target
        for target in LINK.findall(markdown.read_text(encoding="utf-8"))
        if not target.startswith(("http://", "https://", "#"))
    ]


def test_readme_relative_links_resolve():
    missing = [
        target for target in relative_targets(README) if not (ROOT / target).exists()
    ]
    assert missing == []


def test_every_image_is_referenced():
    # docs/superpowers/ の設計書・計画は履歴で、存在しない画像に触れることがあるため対象外。
    referenced = set()
    for markdown in [README, *ROOT.glob("specs/**/*.md")]:
        for target in relative_targets(markdown):
            referenced.add((markdown.parent / target).resolve())
    unreferenced = sorted(
        path.name
        for path in IMAGES.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and path.resolve() not in referenced
    )
    assert unreferenced == []
```

- [ ] **Step 2: テストが失敗することを確認する**

Run:

```bash
source setup_qgis_env.sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_readme_assets.py -q
```

Expected: `test_readme_relative_links_resolve` は PASS、`test_every_image_is_referenced` は FAIL。アサーションの左辺に `browser-file-context-menu.png`、`browser-mesh-index-action-dark.png`、`browser-panel-dark.png`、`mesh-index-qgis.jpg`、`mesh-resource-dialog.jpg`、`processing-load-encoding.png` の 6 件が並ぶ。他の名前が混ざる場合は README か `specs/` の参照漏れなので、削除せずに原因を確認する。

- [ ] **Step 3: 未参照の画像を削除する**

```bash
git rm -q imgs/browser-panel-dark.png imgs/browser-file-context-menu.png imgs/browser-mesh-index-action-dark.png imgs/mesh-index-qgis.jpg imgs/mesh-resource-dialog.jpg imgs/processing-load-encoding.png
ls imgs
```

Expected: `imgs/` に残るのは `browser-file-icons.png`、`browser-loading-indicator.png`、`browser-loading-mode.png`、`browser-mesh-index-action-light.png`、`browser-message-types.png`、`browser-panel-light.png`、`catalog-browser.png`、`loading-settings.png`、`local-storage-setup.png`、`mesh-layer-selection.png`、`mesh-resource-dialog.png`、`processing-download.png` の 12 枚。

- [ ] **Step 4: テストが通ることを確認する**

Run:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_readme_assets.py -q
```

Expected: `2 passed`。

- [ ] **Step 5: lint・フォーマット・全テストを通す**

Run:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests -q
```

Expected: `All checks passed!`、`N files already formatted`、`366 passed`（着手前 364 件 + 2 件）。フォーマット差分が出たら `.venv/bin/ruff format tests/test_readme_assets.py` で直す。

- [ ] **Step 6: コミットする**

```bash
git add tests/test_readme_assets.py
git commit -q -F - <<'EOF'
test: README の相対リンクと imgs/ の被参照を検査し、未参照の画像を削除

README が参照する相対パスの実在と、imgs/ の各ファイルが README か specs/ から
参照されていることを確認する。ダーク版や旧ダイアログなど未参照になった 6 枚を削除した。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
EOF
git status --short
```

Expected: `git status --short` の出力なし（削除は `git rm` でステージ済みのため、このコミットに含まれる）。

---

## 完了時の確認

1. `git log --oneline main..` に設計書・画像とスクリプト・README・テストの 4 コミットが並ぶ。
2. README を GitHub のプレビュー相当（VS Code のプレビューでもよい）で通し読みし、各節が「基本の手順 → 補足」の順で、画像が設計書の位置にある。
3. `git grep -n "（KSJ）" -- README.md imgs` が 0 件。
4. PR 本文には、影響範囲（README・imgs・scripts・tests）、テスト結果（ruff、pytest 366 件）、設計書へのリンク、撮り直した 4 枚の確認結果、残した画像が `specs/` から参照されている旨を書く。インストール節とリリースの仕組みは別仕様で扱う旨を申し送りに書く。
