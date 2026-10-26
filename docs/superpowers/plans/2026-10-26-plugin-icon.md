# プラグインアイコンの適用 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 差し替え済みの配布アイコン（120×120 PNG）を、プラグイン管理・ブラウザパネルのルート・Processing プロバイダ行の 3 か所で表示し、あわせて Processing プロバイダの表示名を「国土数値情報」に揃える。

**Architecture:** アイコンの実体を `ksj/icons/plugin.png` の 1 か所に置き、`ksj/browser_icons.py` の `plugin_icon()` を唯一の読み出し口にする。`metadata.txt` はプラグイン管理用に同じファイルを直接指す。ブラウザのルート項目と Processing プロバイダはどちらも `plugin_icon()` を呼ぶ。

**Tech Stack:** Python 3.9 以上、QGIS 3.44〜4.x（PyQGIS / `qgis.PyQt`）、pytest + pytest-qgis、ruff

**Spec:** `docs/superpowers/specs/2026-10-26-plugin-icon-design.md`

## Global Constraints

- Python は 3.9 以上で動くこと。`tomllib`、`match` 文、`X | Y` 形式の型注釈は使えない。
- パッケージ内部は相対インポート（`from .browser_icons import plugin_icon`）。Plugin Reloader のリロード互換のため。
- Qt は `qgis.PyQt` 経由で import する（Qt5・Qt6 両対応のため）。`from PyQt5...` は書かない。
- アイコンの実体は `ksj/icons/` に置く。`imgs/` はドキュメント用画像のみ（AGENTS.md）。
- Processing プロバイダの `id()` は `"ksj"` から変えない。`ksj:search_datasets` 等のアルゴリズム ID を壊さない。
- 4 つのアルゴリズムに `icon()` は実装しない。QGIS 既定の歯車のままにする。
- `specs/` 配下の「国土数値情報（KSJ）」という記述は移行前の設計履歴なので変えない。
- インデントは 4 スペース。`snake_case` 関数、`CamelCase` クラス、`UPPER_SNAKE_CASE` 定数。
- コミットは Conventional Commits。タイプは小文字、要約は 50 文字程度、本文は日本語。
- `uv run` は使わない。`uv.lock` を書き換えることがあるため、`.venv` のバイナリを直接呼ぶ。

**よく使うコマンド**

```bash
# テスト（ホスト。source はシェルごとに必要）
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest <対象> -q

# Lint
.venv/bin/ruff check .
.venv/bin/ruff format --check .

# テスト（Docker・CI と同じ経路）
bash scripts/test-docker.sh
```

---

### Task 1: 配布アイコンを `ksj/icons` へ移し、`metadata.txt` を向け直す

プラグイン管理（インストール画面）に出るアイコンを、新しい置き場所から参照させる。

**Files:**
- Rename: `imgs/icon.png` → `ksj/icons/plugin.png`
- Modify: `metadata.txt:33`
- Test: `tests/test_metadata.py`（末尾に 1 テスト追加）

**Interfaces:**
- Consumes: なし
- Produces: `ksj/icons/plugin.png` — 120×120 の RGBA PNG。Task 2 の `plugin_icon()` がこのパスを読む。

- [ ] **Step 1: アイコンを移動する**

`imgs/icon.png` には未コミットの差し替えが入っている。`git mv` は作業ツリーの変更ごと移すので、そのまま実行してよい。

```bash
git mv imgs/icon.png ksj/icons/plugin.png
file ksj/icons/plugin.png
```

期待する出力: `ksj/icons/plugin.png: PNG image data, 120 x 120, 8-bit/color RGBA, non-interlaced`

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_metadata.py` の末尾（35 行目の後）に追加する。`load_metadata()` と `METADATA` は同ファイルに既にある。

```python


def test_icon_file_exists():
    # icon はプラグインディレクトリからの相対パス。
    assert (METADATA.parent / load_metadata()["icon"]).is_file()
```

- [ ] **Step 3: テストを走らせて失敗を確認する**

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py::test_icon_file_exists -q
```

期待: FAIL。`metadata.txt` はまだ `imgs/icon.png` を指しているが、その実体は移動済みで存在しない。

- [ ] **Step 4: `metadata.txt` を向け直す**

33 行目を書き換える。

変更前:
```ini
icon=imgs/icon.png
```

変更後:
```ini
icon=ksj/icons/plugin.png
```

他の行は触らない。

- [ ] **Step 5: テストを走らせて成功を確認する**

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py -q
```

期待: PASS。`4 passed`。

- [ ] **Step 6: コミットする**

`git mv` は改名をステージするが、インデックスに載るのは移動前の blob で、差し替え済みの画像は新パスに対する未ステージ変更として残る。アイコン本体も明示的に `git add` すること。

```bash
git add ksj/icons/plugin.png metadata.txt tests/test_metadata.py
git status --short
```

期待する `git status --short`:
```
R  imgs/icon.png -> ksj/icons/plugin.png
M  metadata.txt
M  tests/test_metadata.py
```

ステージされた中身が差し替え後のものかを確かめる。画像の中身が大きく変わるため、改名として検出されず `D`+`A` で出ることもある。

```bash
git show :ksj/icons/plugin.png | file -
```

期待: `PNG image data, 120 x 120, 8-bit/color RGBA, non-interlaced`

```bash
git commit -F- <<'MSG'
feat: プラグインアイコンを ksj/icons に置き直す

差し替えた 120x120 の PNG を ksj/icons/plugin.png へ移し、metadata.txt を
そちらに向ける。AGENTS.md の「アイコンは ksj/icons、imgs はドキュメント用
画像」に合わせ、コードが読む実体とメタデータの参照先を 1 ファイルにまとめる。
metadata.txt の icon が実在することを確認するテストを足した。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
MSG
```

---

### Task 2: ブラウザパネルのルートを配布アイコンにする

ブラウザパネルの「国土数値情報」の左に出るアイコンを、線画 SVG から配布アイコンへ替える。共有アクセサ `plugin_icon()` もここで作る。

**Files:**
- Modify: `ksj/browser_icons.py:1`（docstring）と `browser_icon()` の後ろ（関数 1 つ追加）
- Modify: `ksj/browser.py:7`（import）、`ksj/browser.py:32`（`setIcon`）
- Delete: `ksj/icons/catalog.svg`
- Test: `tests/test_catalog_browser.py`（import 1 行と末尾に 1 テスト追加）

**Interfaces:**
- Consumes: `ksj/icons/plugin.png`（Task 1）
- Produces: `ksj.browser_icons.plugin_icon()` — 引数なし。`ksj/icons/plugin.png` を読んだ `QIcon` を返す。Task 3 が呼ぶ。

- [ ] **Step 1: 共有アクセサを追加する**

これはテストが参照する足場で、単体では赤にならない。`ksj/browser_icons.py` の 1 行目の docstring を差し替える。

変更前:
```python
"""ブラウザの役割を示す、明暗どちらの背景でも読める線画アイコン。"""
```

変更後:
```python
"""プラグインのアイコン。配布アイコンと、明暗どちらの背景でも読める線画アイコン。"""
```

続いて `browser_icon()` の定義の直後（`def file_icon(path):` の前）に関数を足す。トップレベルの定義どうしなので、前後は空行 2 行で区切る。`ICON_DIR` と `QIcon` は同ファイルに既にある。`browser_icon()` は拡張子を `.svg` に固定しているので、PNG は別の関数で扱う。

```python
def plugin_icon():
    """プラグインを表すアイコン。ブラウザのルートと Processing プロバイダで共有する。"""
    return QIcon(str(ICON_DIR / "plugin.png"))
```

- [ ] **Step 2: 失敗するテストを書く**

まず `tests/test_catalog_browser.py` の 15 行目（`from ksj.browser import KsjDataItemProvider, KsjRootItem`）の直後に import を足す。

```python
from ksj.browser_icons import plugin_icon
```

次にファイル末尾にテストを追加する。`icon_image()` は `tests/helpers.py` の既存ヘルパで、`item.icon().pixmap(24, 24).toImage()` を返す。

```python


def test_root_uses_the_plugin_icon(qgis_app):
    """ルート項目はプラグインの配布アイコンを出す。"""
    item = KsjRootItem()
    assert not plugin_icon().isNull()
    assert icon_image(item) == plugin_icon().pixmap(24, 24).toImage()
```

- [ ] **Step 3: テストを走らせて失敗を確認する**

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_catalog_browser.py::test_root_uses_the_plugin_icon -q
```

期待: FAIL。最後の assert で AssertionError。ルートはまだ `catalog.svg` の線画を出しており、画像が一致しない。1 つ目の `isNull()` の assert は通る。

- [ ] **Step 4: ルートのアイコンを差し替える**

`ksj/browser.py` の 7 行目。`browser_icon` の利用箇所はこの後の 1 か所だけなので、import ごと入れ替える。

変更前:
```python
from .browser_icons import browser_icon
```

変更後:
```python
from .browser_icons import plugin_icon
```

同ファイル 32 行目、`KsjRootItem.__init__` の中。

変更前:
```python
        self.setIcon(browser_icon("catalog"))
```

変更後:
```python
        self.setIcon(plugin_icon())
```

- [ ] **Step 5: テストを走らせて成功を確認する**

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_catalog_browser.py -q
```

期待: PASS。`32 passed`。

- [ ] **Step 6: 未使用になった線画を消す**

`catalog.svg` はルート項目専用だった。参照が残っていないことを確かめてから消す。

```bash
git grep -n 'browser_icon("catalog")'
git grep -n "catalog\.svg" -- ':!docs/superpowers/'
```

期待: どちらも出力なし（終了コードは 1）。追跡ファイルだけを見るため `git grep` を使う。設計書は `catalog.svg` に言及しているので除外する。

```bash
git rm ksj/icons/catalog.svg
```

- [ ] **Step 7: ブラウザ関連のテストと lint を通す**

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_catalog_browser.py tests/test_browser_items.py tests/test_lazy_loading.py -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

期待: テストは全件 PASS。ruff は `All checks passed!` と `N files already formatted`。

- [ ] **Step 8: コミットする**

```bash
git add ksj/browser_icons.py ksj/browser.py tests/test_catalog_browser.py
git commit -F- <<'MSG'
feat: ブラウザのルートに配布アイコンを表示する

ブラウザパネルの「国土数値情報」の左を線画 SVG から配布アイコンへ替える。
読み出し口として browser_icons.plugin_icon() を足し、Processing
プロバイダとも共有できるようにした。専用だった icons/catalog.svg は
参照がなくなるので削除する。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
MSG
```

---

### Task 3: Processing プロバイダにアイコンと表示名を与える

Processing ツールボックスのプロバイダ行に配布アイコンを出し、表示名をブラウザのルートと同じ「国土数値情報」に揃える。

**Files:**
- Modify: `ksj/processing_provider.py:3-18`
- Modify: `README.md:91`
- Test: `tests/test_processing.py`（`test_provider_is_discoverable` の直後に 1 テスト追加）

**Interfaces:**
- Consumes: `ksj.browser_icons.plugin_icon()`（Task 2）
- Produces: なし

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_processing.py` の 42 行目（`test_provider_is_discoverable` の本体）の後ろに追加する。`processing_provider` は `tests/conftest.py` の既存フィクスチャで、`KsjProcessingProvider` の実体を返す。

```python


def test_provider_is_named_and_iconed_for_the_toolbox(processing_provider):
    """ツールボックスの見出しはブラウザのルートと同じ表記で、配布アイコンを出す。"""
    assert processing_provider.id() == "ksj"
    assert processing_provider.name() == "国土数値情報"
    assert not processing_provider.icon().isNull()
```

`id()` も確かめるのは、表示名を変えたときにアルゴリズム ID まで一緒に変えてしまう事故を防ぐため。

- [ ] **Step 2: テストを走らせて失敗を確認する**

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest "tests/test_processing.py::test_provider_is_named_and_iconed_for_the_toolbox" -q
```

期待: FAIL。`AssertionError: assert '国土数値情報（KSJ）' == '国土数値情報'`。

- [ ] **Step 3: プロバイダを実装する**

`ksj/processing_provider.py` の全文を次にする。`id()` と `loadAlgorithms()` は変えない。`longName()` は実装せず、既定として `name()` が返る。

```python
"""国土数値情報の検索・取得を公開する Processing プロバイダ。"""

from qgis.core import QgsProcessingProvider

from .browser_icons import plugin_icon
from .processing_algorithms import (
    DownloadResource,
    ListResources,
    LoadLayer,
    SearchDatasets,
)


class KsjProcessingProvider(QgsProcessingProvider):
    def id(self):
        return "ksj"

    def name(self):
        return "国土数値情報"

    def icon(self):
        return plugin_icon()

    def loadAlgorithms(self):
        for algorithm in (SearchDatasets, ListResources, DownloadResource, LoadLayer):
            self.addAlgorithm(algorithm())
```

- [ ] **Step 4: テストを走らせて成功を確認する**

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_processing.py -q
```

期待: PASS。全件通る。

- [ ] **Step 5: README を直す**

`README.md` の 91 行目。

変更前:
```markdown
プラグインを有効化すると、Processingツールボックスの「国土数値情報（KSJ）」に4つの処理が表示されます。更新後はプラグインを再読み込みしてください。
```

変更後:
```markdown
プラグインを有効化すると、Processingツールボックスの「国土数値情報」に4つの処理が表示されます。更新後はプラグインを再読み込みしてください。
```

README の他の行と `specs/` 配下は触らない。

- [ ] **Step 6: 残りの旧表記を確認する**

```bash
git grep -n "国土数値情報（KSJ）" -- ':!specs/' ':!docs/superpowers/'
```

期待: 出力なし。着手前は `README.md:91` と `ksj/processing_provider.py:18` の 2 件が出る。`specs/` と `docs/superpowers/`（設計書・本計画）の記述は残す。

- [ ] **Step 7: コミットする**

```bash
git add ksj/processing_provider.py tests/test_processing.py README.md
git commit -F- <<'MSG'
feat: Processing プロバイダにアイコンと名前を与える

ツールボックスのプロバイダ行に配布アイコンを出し、表示名を
「国土数値情報（KSJ）」から「国土数値情報」へ替えてブラウザのルートと
揃える。id() は "ksj" のままなので ksj:search_datasets 等の
アルゴリズム ID と既存のモデルは影響を受けない。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
MSG
```

---

### Task 4: 仕上げの検証

コード変更はない。設計書の「検証」を上から実行し、結果を記録する。

**Files:**
- Modify: なし

**Interfaces:**
- Consumes: Task 1〜3 の成果
- Produces: なし

- [ ] **Step 1: lint を通す**

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

期待: `All checks passed!` と `N files already formatted`。

- [ ] **Step 2: ホストで全テストを通す**

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests -q
```

期待: `363 passed`。着手前が 360 件で、本計画で 3 件（`test_icon_file_exists`、`test_root_uses_the_plugin_icon`、`test_provider_is_named_and_iconed_for_the_toolbox`）増える。落ちた場合は失敗の出力をそのまま残し、原因を切り分けてから次へ進む。

- [ ] **Step 3: 旧パスが残っていないことを確認する**

```bash
git grep -n "imgs/icon.png" -- ':!docs/superpowers/'
```

期待: 出力なし。着手前は `metadata.txt:33` の 1 件が出る。設計書と本計画には `imgs/icon.png` の記述が残るので除外する。

- [ ] **Step 4: Docker（CI と同じ経路）で全テストを通す**

```bash
bash scripts/test-docker.sh
```

期待: QGIS 3.44 で全件 PASS。Apple Silicon では AMD64 エミュレーションが要るため時間がかかる。CI では 3.44・4.0・4.2 で実行される。

- [ ] **Step 5: 実機確認を依頼する**

ここは利用者（山﨑さん）にお願いする。QGIS を再起動したうえで次の 3 か所を見てもらう。プラグイン管理はアイコンをキャッシュするため、再起動が要る。

1. プラグイン管理の一覧と詳細欄に新しいアイコンが出る
2. ブラウザパネルの「国土数値情報」の左に新しいアイコンが出る
3. Processing ツールボックスに「国土数値情報」という見出しで、新しいアイコン付きの行が出る。配下の 4 つの処理は QGIS 既定の歯車のまま

明るいテーマと暗いテーマの両方で読めることもあわせて見てもらう。

- [ ] **Step 6: PR を作る**

ブランチは `feat/plugin-icon`。PR 本文には影響範囲、実行したテストコマンドと結果、設計書 `docs/superpowers/specs/2026-10-26-plugin-icon-design.md` へのリンク、そして次の申し送りを書く。

> `imgs/browser-panel-light.png` と `imgs/browser-panel-dark.png` はルート行のアイコンが旧アイコンのままです。これらはルート名も「国土数値情報（KSJ）」のままで既に古くなっており、撮り直しは別途まとめて行います。

PR 本文の末尾に付けるもの:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
```
