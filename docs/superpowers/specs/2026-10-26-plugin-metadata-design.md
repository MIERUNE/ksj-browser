# プラグイン定義ファイルの実態合わせ 設計

日付: 2026-10-26
対象: `metadata.txt`、`pyproject.toml`、および名称統一に伴う付随ファイル

## 目的

`metadata.txt` と `pyproject.toml` はプラグインテンプレート由来の仮の値（`KSJ-Provider`、`qgis-plugin-template`、英語の説明文、空の作者・URL、存在しないリリースワークフローへの言及）のまま残っている。両ファイルをプラグインの実態に合わせ、あわせてリポジトリ内の識別子を `ksj-provider` から `ksj-browser` に統一する。

## 決定事項

| 項目 | 値 | 理由 |
| --- | --- | --- |
| プラグイン表示名 `name` | `国土数値情報ブラウザ` | ブラウザのルート項目と同じ日本語名で、QGIS のプラグイン一覧で探しやすい |
| 識別子（pyproject の `name`、README 題名、パス、URL） | `ksj-browser` | GitHub リポジトリ `MIERUNE/ksj-browser` と一致させる。新規 clone のディレクトリ名もこれになる |
| `version` | `0.1.0`（両ファイル共通） | リリース用ワークフローは存在しない。リリース時に両ファイルを手で更新する |
| `author` / `email` | `MIERUNE Inc.` / `info@mierune.co.jp` | 組織リポジトリに合わせる |
| `homepage` / `repository` / `tracker` | `https://github.com/MIERUNE/ksj-browser`（tracker は `/issues`） | 実在するリポジトリ |
| `category` | `Web` | 利用者の指定。GTFS-GO と同じ |
| `experimental` | `False` | 明示する。GTFS-GO と同じ |
| `supportsQt6` | 書かない | QGIS 4.0 正式版で無効化済み。`tests/test_metadata.py` が不在を検証している |
| `plugin_dependencies` | 書かない | kumoy は任意の追加方法で、書くとインストール時に必須扱いになる |
| `changelog` | コメントのまま | CHANGELOG が存在しない |
| 書式 | [MIERUNE/GTFS-GO の metadata.txt](https://github.com/MIERUNE/GTFS-GO/blob/main/metadata.txt) に倣う | 社内プラグインと並びを揃える。テンプレート由来の改行抜け（`plugin.# Mandatory items:`）は 2 行に分ける |

## 変更内容

### metadata.txt（全文）

```ini
# This file contains metadata for your plugin.

# This file should be included when you package your plugin.
# Mandatory items:

[general]
name=国土数値情報ブラウザ
qgisMinimumVersion=3.44
qgisMaximumVersion=4.99
description=国土数値情報（国土交通省）のデータを QGIS のブラウザパネルと Processing から検索・取得して地図に追加します。
# pyproject.toml の version と揃える。リリース時に両方を手で更新する。
version=0.1.0
author=MIERUNE Inc.
email=info@mierune.co.jp

about=国土数値情報ダウンロードサイトの現行形式・過年度版・旧形式を、QGIS のブラウザパネルから分類・年度・地域別に探し、必要なファイルだけを部分取得して地図に追加します。配布メッシュを地図上でクリックして追加する索引、Processing ツールボックスからの検索・取得・読み込み、フォルダ保存・一時レイヤー・kumoy へのアップロードの追加方法に対応します。公式一覧の分類と配布ファイル情報を同梱し、起動時に全データをダウンロードする必要はありません。QGIS 3.44 以上 4.x まで（Qt 5・Qt 6）に対応します。

tracker=https://github.com/MIERUNE/ksj-browser/issues
repository=https://github.com/MIERUNE/ksj-browser
# End of mandatory metadata

# Recommended items:

hasProcessingProvider=yes
# Uncomment the following line and add your changelog:
# changelog=

# Tags are comma separated with spaces allowed
tags=python, japan, ksj, 国土数値情報, mlit, browser, processing, download, vector, raster, mesh

homepage=https://github.com/MIERUNE/ksj-browser
category=Web
icon=imgs/icon.png
# experimental flag
experimental=False
```

`hasProcessingProvider=yes`（`ksj/processing_provider.py` が存在）と `icon=imgs/icon.png`（ファイルが存在）は現状どおり。

### pyproject.toml（全文）

```toml
[project]
name = "ksj-browser"
version = "0.1.0"
description = "国土数値情報ブラウザ: 国土数値情報のデータを QGIS のブラウザパネルと Processing から利用する QGIS プラグイン"
readme = "README.md"
requires-python = ">=3.9"
# QGIS 内で動くプラグインのため、実行時の pip 依存はない。
# QGIS 同梱の qgis・osgeo・processing と標準ライブラリだけを使う。
dependencies = []

[dependency-groups]
# uv sync で入れる開発依存。テスト依存の固定は requirements-test.txt（Docker・ホスト共用）と揃える。
dev = [
    "ruff>=0.14.11",
    "pyqt5-stubs>=5.15.6.0",
    "pytest>=8,<10",
    "pytest-cov==7.1.0",
    "pytest-qgis==2.1.0; python_version < '3.10'",
    "pytest-qgis==5.0.2; python_version >= '3.10'",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

根拠:

- プラグインが import する外部モジュールは `qgis`・`osgeo`・`processing`・`pyplugin_installer` と標準ライブラリだけで、pip 依存はない。`dependencies` にあった `pytest-qgis` は誤り。
- pyproject の実際の用途は、`uv sync --locked` による lint 環境（CI の Lint ジョブと README の手順）と、pytest の設定。dev グループは `requirements-test.txt` と同じ固定（`pytest>=8,<10`、`pytest-cov==7.1.0`、`pytest-qgis` の Python バージョン別固定）に揃える。`pytest-cov==7.1.0` は Python 3.9 に対応している。
- `uv sync` は既定でロックにないパッケージを環境から削除する。dev グループに `pytest-cov` がない現状では、ホストの `.venv` に `uv pip install -r requirements-test.txt` で入れた `pytest-cov` が `uv sync` で消える。揃えることでこの罠をなくす。
- `[tool.ruff]` は追加しない。Ruff は `requires-python` から対象バージョンを推定しており、既定設定で運用しているのが実態。
- `name` は Python のパッケージ名規則で ASCII に限られるため日本語名は使えない。

### uv.lock

`uv lock` で再生成する。ロックには旧名 `qgis-plugin-template` のプロジェクト項目が記録されており、名前を変えたまま再生成しないと CI の `uv sync --locked` が失敗する。`pytest-cov` と `pytest-qgis 5.0.2` の解決にネットワークを使う。

### requirements-test.txt

先頭コメントに「`pyproject.toml` の dev グループと同じ固定にする」と 1 行足し、相互参照にする。固定値は変えない。

### plugin.py

未使用の定数 `PLUGIN_NAME = "KSJ-Provider"` を `"国土数値情報ブラウザ"` にする。

### ksj/browser.py

`KsjDataItemProvider.name()` の戻り値 `"KSJ Provider"` を `"国土数値情報ブラウザ"` にする。`QgsDataItemProvider.name()` は人間向けのラベルで、画面表示や設定キーには使われていないため挙動は変わらない。

### tests/test_metadata.py

モジュール docstring を「metadata.txt が QGIS 3.44 から 4.x までの読み込み条件を満たし、pyproject.toml と版が揃っていること」に改め、次のテストを足す。Python 3.9 には `tomllib` がないため正規表現で読む。

```python
import re

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version_matches_pyproject():
    # リリース時は metadata.txt と pyproject.toml の両方を手で更新する。
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    assert match is not None
    assert load_metadata()["version"] == match.group(1)
```

既存の 2 テスト（バージョン範囲、`supportsQt6` 不在）は変えない。

### `ksj-provider` → `ksj-browser` の統一

追跡ファイル中の識別子・URL・パスをすべて置き換える。完了条件は `git grep -i ksj-provider` が 0 件になること。

| ファイル | 箇所 |
| --- | --- |
| `README.md` | 1 行目の題名を `# ksj-browser — 国土数値情報ブラウザ（QGIS プラグイン）` に。Windows 手順の `cd C:\path\to\ksj-provider` |
| `.github/agents/copilot-instructions.md` | 1 行目の見出し |
| `.specify/memory/constitution.md` | 1 行目の見出し |
| `specs/004-complete-catalog/verification.md` | Issue #2〜#6 の URL（5 か所） |
| `specs/004-complete-catalog/review-followups.md` | Issue #6 の URL |
| `specs/001-update-dosyasaigai-script/tasks.md` | T016 の `ksj-provider` |
| `specs/003-school-data/quickstart.md` | `cd /path/to/ksj-provider` |
| `docs/superpowers/plans/2026-10-23-issue-6.md` | Issue #6 の URL |
| `docs/superpowers/plans/2026-10-24-qgis4-migration.md` | `ln -s … /plugins/ksj-provider` のパス |
| `docs/superpowers/specs/2026-10-24-qgis4-migration-design.md` | `ln -s … /plugins/ksj-provider` のパス |

### 変えないもの

- `KsjDataItemProvider`、`KsjProcessingProvider`、`PROVIDER_KEY = "ksj"`。QGIS のプロバイダという概念の名前であり、プラグイン名ではない。
- QGIS 4 移行の設計書・計画書にある `name=KSJ-Provider` の引用と「プラグイン管理で KSJ-Provider が一覧に出ること」の検証記述、`specs/001-zip-recursive-browse/quickstart.md` の「KSJ Provider」。当時の表示名の記録として残す。
- `.codex/config.toml` の旧パス。git 管理外。

## 検証

1. `uv lock` の後に `uv sync --locked` を実行し、CI の Lint ジョブと同じ手順でロックが解決すること。ホストの `.venv` では `pytest-cov` が 2.10.0 から 7.1.0 に入れ替わる。
2. `.venv/bin/ruff check .` と `.venv/bin/ruff format --check .` が通ること。
3. `source setup_qgis_env.sh` のうえで `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py -q` が通ること。
4. `git grep -i ksj-provider` が 0 件であること。`git grep -n 'KSJ.Provider'` の残りが「変えないもの」に挙げた歴史的記述だけであること。
5. 可能なら `bash scripts/test-docker.sh tests/test_metadata.py -q` で Docker（QGIS 3.44）でも確認する。CI では 3 バージョンで実行される。

## 範囲外と申し送り

- README は MIT ライセンスと記載しているが、リポジトリに LICENSE ファイルがなく GitHub 上もライセンス未検出。別途 LICENSE を追加する判断が必要。
- リリース用ワークフロー（タグからの version 埋め込み）は作らない。必要になれば別タスク。
- ローカルの作業ディレクトリ `~/Documents/GitHub/ksj-provider` と、QGIS3・QGIS4 両プロファイルの `python/plugins/ksj-provider` シンボリックリンクは旧名のまま。QGIS はフォルダ名でプラグインを識別するため、リンク名を `ksj-browser` に変えた後はプラグイン管理で一度有効化し直す。実装完了後に手順を案内する。
