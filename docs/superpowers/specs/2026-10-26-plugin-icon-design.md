# プラグインアイコンの適用 設計

日付: 2026-10-26
対象: `imgs/icon.png`（差し替え済み）、`metadata.txt`、`ksj/browser_icons.py`、`ksj/browser.py`、`ksj/processing_provider.py`、`ksj/icons/catalog.svg`、`tests/`、`README.md`

## 目的

利用者が差し替えた新しいアイコン（120×120 PNG、背景透過、角丸の濃いティール地に地図とピン）を、プラグインが姿を見せる 3 か所すべてで表示する。あわせて Processing プロバイダの表示名をブラウザのルート項目と揃える。

対象の 3 か所:

| 表示場所 | 現状 |
| --- | --- |
| プラグイン管理（インストール画面） | `metadata.txt` の `icon=imgs/icon.png` を参照。配線済みで、差し替えだけで絵は変わる |
| ブラウザパネルのルート「国土数値情報」 | `ksj/browser.py` が線画 SVG `ksj/icons/catalog.svg` を指定 |
| Processing ツールボックスのプロバイダ行 | `QgsProcessingProvider.icon()` が未実装で、QGIS 既定のアイコンが出る |

## 決定事項

| 項目 | 決定 | 理由 |
| --- | --- | --- |
| アイコンの置き場所 | `imgs/icon.png` → `ksj/icons/plugin.png`（`git mv`） | AGENTS.md が「アイコンは `ksj/icons/`、`imgs/` にはドキュメント用画像を置きます」と定めている。コードが読む実体と `metadata.txt` の参照先が 1 ファイルに集約される |
| 共通アクセサの置き場所 | `ksj/browser_icons.py` に `plugin_icon()` を追加 | `ICON_DIR` が既にこのモジュールにある。`ksj/icons.py` という新規モジュールは `ksj/icons/` ディレクトリと名前が衝突するため作れない |
| アイコンの形式 | PNG のまま（SVG 化しない） | 120×120 は 16px のブラウザ項目でもピンの形が判別でき、64px 前後のプラグイン管理詳細欄でも劣化しない。背景が透過で地色が濃いティールのため、QGIS の明暗どちらのテーマでも読める |
| Processing のアイコン適用範囲 | プロバイダ行のみ。4 つのアルゴリズムは QGIS 既定の歯車のまま | 利用者の指定。QGIS 標準プロバイダと姉妹プラグイン kumoy（`processing/provider.py` で `icon()` のみ実装）に合わせる。同じ絵が 5 行並ぶと各処理を見分けにくい |
| プロバイダの `name()` | `国土数値情報（KSJ）` → `国土数値情報` | 利用者の指定。ブラウザのルート項目と同じ表記に揃う |
| プロバイダの `id()` | `"ksj"` のまま | `ksj:search_datasets` 等のアルゴリズム ID、既存のモデルビルダー、README のコード例を壊さない |
| `ksj/icons/catalog.svg` | 削除 | ルート項目専用で、参照は `ksj/browser.py` の 1 か所だけ。差し替え後は未使用になる |

## 変更内容

### imgs/icon.png → ksj/icons/plugin.png

`git mv imgs/icon.png ksj/icons/plugin.png`。差し替え済みの 120×120 PNG をそのまま移す。内容は変更しない。

### metadata.txt

```ini
icon=ksj/icons/plugin.png
```

`icon` はプラグインディレクトリからの相対パス。他の項目は変えない。

### ksj/browser_icons.py

モジュール docstring を、線画アイコン専用から、プラグインが使うアイコン全般を扱う旨に広げる。

```python
"""プラグインのアイコン。配布アイコンと、明暗どちらの背景でも読める線画アイコン。"""
```

`browser_icon()` の下に追加する。

```python
def plugin_icon():
    """プラグインを表すアイコン。ブラウザのルートと Processing プロバイダで共有する。"""
    return QIcon(str(ICON_DIR / "plugin.png"))
```

`browser_icon()` は拡張子を `.svg` に固定しているため、PNG は別の関数で扱う。

### ksj/browser.py

import と `KsjRootItem.__init__` の 1 行を差し替える。`browser_icon` の利用箇所はこの 1 か所だけなので、import ごと入れ替える。

```python
from .browser_icons import plugin_icon
```

```python
        self.setIcon(plugin_icon())
```

### ksj/processing_provider.py

`icon()` を追加し、`name()` の戻り値を変える。

```python
from .browser_icons import plugin_icon


class KsjProcessingProvider(QgsProcessingProvider):
    def id(self):
        return "ksj"

    def name(self):
        return "国土数値情報"

    def icon(self):
        return plugin_icon()
```

`id()` と `loadAlgorithms()` は変えない。`longName()` は未実装のままで、既定として `name()` を返す。

### ksj/icons/catalog.svg

削除する。

### tests/test_metadata.py

`metadata.txt` の `icon` が指すファイルの実在を確認するテストを足す。パスを移したまま `metadata.txt` を直し忘れる事故を防ぐ。

```python
def test_icon_file_exists():
    # icon はプラグインディレクトリからの相対パス。
    assert (METADATA.parent / load_metadata()["icon"]).is_file()
```

既存の 3 テストは変えない。

### tests/test_processing.py

プロバイダの表示名とアイコンを確認するテストを足す。`processing_provider` フィクスチャは `KsjProcessingProvider` の実体を返す。

```python
def test_provider_is_named_and_iconed_for_the_toolbox(processing_provider):
    assert processing_provider.id() == "ksj"
    assert processing_provider.name() == "国土数値情報"
    assert not processing_provider.icon().isNull()
```

`id()` も確認するのは、表示名を変えたときにアルゴリズム ID まで一緒に変えてしまう事故を防ぐため。

### tests/test_catalog_browser.py

ルート項目が配布アイコンを使うことを確認するテストを足す。既存の `tests/helpers.icon_image` と同じ方法で画像に落として比較する。

```python
def test_root_uses_the_plugin_icon(qgis_app):
    item = KsjRootItem()
    assert icon_image(item) == plugin_icon().pixmap(24, 24).toImage()
```

`ksj.browser_icons.plugin_icon` の import を足す。既存のアイコン関連テスト（ファイル形式別アイコン、ジオメトリ非依存のベクタアイコン）は変えない。

### README.md

91 行目の「Processingツールボックスの「国土数値情報（KSJ）」に4つの処理が表示されます」を「Processingツールボックスの「国土数値情報」に4つの処理が表示されます」にする。

## 変えないもの

- `specs/` 配下の「国土数値情報（KSJ）」という記述。移行前の設計履歴であり、当時の表示名の記録として残す。
- `PROVIDER_KEY = "ksj"`、`KsjProcessingProvider` などのクラス名・識別子。
- 4 つのアルゴリズムの `icon()`。実装しないので QGIS 既定の歯車のまま。
- `imgs/` の他の画像と、それを参照する README の行。

## 検証

1. `.venv/bin/ruff check .` と `.venv/bin/ruff format --check .` が通ること。
2. `source setup_qgis_env.sh` のうえで `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py tests/test_processing.py tests/test_catalog_browser.py -q` が通ること。
3. `bash scripts/test-docker.sh` で QGIS 3.44 の全テストが通ること。CI では 3.44・4.0・4.2 で実行される。
4. この設計書と実装計画を除いて `git grep -n "imgs/icon.png"` が 0 件であること。
5. 実機確認（利用者にお願いする）: QGIS を再起動し、(a) プラグイン管理の一覧と詳細欄、(b) ブラウザパネルの「国土数値情報」の左、(c) Processing ツールボックスの「国土数値情報」の行、の 3 か所に新しいアイコンが出ること。明るいテーマと暗いテーマの両方で読めること。

## 範囲外と申し送り

- `imgs/browser-panel-light.png`、`imgs/browser-panel-dark.png` などブラウザパネルを写した README のスクリーンショットは、ルート行のアイコンが旧アイコンのままになる。これらは既にルート名が「国土数値情報（KSJ）」のままで古くなっており（コードは既に「国土数値情報」）、今回のアイコン変更でズレが 2 つになる。撮り直しは QGIS の起動と撮影の工程が必要で PR の守備範囲が広がるため、今回は行わず、PR に既知のズレとして記載して別途まとめて更新する。
- アルゴリズム 1 つずつに固有のアイコンを与える案は採らない。必要になれば別タスク。
