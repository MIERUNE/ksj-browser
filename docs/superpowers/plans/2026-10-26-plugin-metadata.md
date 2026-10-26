# プラグイン定義ファイルの実態合わせ 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `metadata.txt` と `pyproject.toml` をプラグインの実態（表示名・版・作者・URL・依存関係）に合わせ、リポジトリ内の識別子を `ksj-provider` から `ksj-browser` に統一する。

**Architecture:** 変更はすべて定義ファイルと文字列の置き換えで、ロジックの変更はない。Task 1 で `metadata.txt` を全文書き換え、版が `pyproject.toml` と揃うことをテストで固定する。Task 2 で `pyproject.toml` を書き換えて `uv.lock` を再生成し、CI と同じ `uv sync --locked` が通ることを確認する。Task 3 で識別子と表示名定数を置き換え、Task 4 で全テストを流す。

**Tech Stack:** QGIS プラグイン（Python 3.9 以上、PyQGIS）、uv 0.13、pytest / pytest-qgis、Ruff

**Spec:** `docs/superpowers/specs/2026-10-26-plugin-metadata-design.md`

## Global Constraints

- 対応 QGIS は `qgisMinimumVersion=3.44`、`qgisMaximumVersion=4.99`。`supportsQt6` は書かない（`tests/test_metadata.py` が不在を検証する）。
- プラグイン表示名は `国土数値情報ブラウザ`。識別子（pyproject の `name`、README 題名、パス、URL）は `ksj-browser`。
- `version` は `metadata.txt` と `pyproject.toml` の両方で `0.1.0`。
- `author=MIERUNE Inc.`、`email=info@mierune.co.jp`、`homepage` / `repository` は `https://github.com/MIERUNE/ksj-browser`、`tracker` はその `/issues`。`category=Web`、`experimental=False`。
- 実行時の pip 依存はない（`dependencies = []`）。dev グループの固定は `requirements-test.txt` と同じ値にする。
- `KsjDataItemProvider`、`KsjProcessingProvider`、`PROVIDER_KEY = "ksj"` は変えない。QGIS 4 移行の設計書・計画書と `specs/001-zip-recursive-browse/quickstart.md` にある旧表示名 `KSJ-Provider` / `KSJ Provider` の記述も変えない。
- ホスト環境: macOS、`.venv` は QGIS 付属 Python 3.9.5 を `--system-site-packages` で使う uv 製の仮想環境（`.venv/pyvenv.cfg` に `include-system-site-packages = true`）。テストと Ruff は `.venv/bin/...` を直接呼ぶ。`uv run` はロックファイルを書き換えることがあるので使わない。
- テストは `source setup_qgis_env.sh` で環境変数を入れ、`QT_QPA_PLATFORM=offscreen` を付けて実行する。
- コミットは Conventional Commits（小文字タイプ、日本語要約）。末尾に次のトレーラーを付ける。

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QAxRr2rTyYHn1s7hzJt48Y
```

- 作業ブランチは `chore/plugin-metadata`（設計書のコミット a7ed59a を含む）。`main` には直接コミットしない。

---

### Task 1: metadata.txt の全文書き換えと版一致テスト

**Files:**
- Modify: `metadata.txt`（全文置換）
- Test: `tests/test_metadata.py`

**Interfaces:**
- Consumes: なし
- Produces: `metadata.txt` の `[general]` に `version=0.1.0`。Task 2 の `pyproject.toml` はこの値と一致させる。`tests/test_metadata.py::load_metadata()`（既存。`configparser` で `[general]` を返す）

- [ ] **Step 1: 版一致テストを追加する（失敗するテスト）**

`tests/test_metadata.py` を次の全文にする。既存の 2 テストは変えず、docstring と `import re`、`PYPROJECT`、`test_version_matches_pyproject` を足す。

```python
"""metadata.txt が QGIS 3.44 から 4.x までの読み込み条件を満たし、pyproject.toml と版が揃っていること。"""

import configparser
import re
from pathlib import Path

METADATA = Path(__file__).resolve().parents[1] / "metadata.txt"
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def load_metadata():
    parser = configparser.ConfigParser()
    parser.read(METADATA, encoding="utf-8")
    return parser["general"]


def test_version_range_covers_qgis_3_and_4():
    general = load_metadata()
    assert general["qgisMinimumVersion"] == "3.44"
    # qgisMaximumVersion が無いと QGIS 4 は上限を 3.99 とみなして読み込まない。
    assert general["qgisMaximumVersion"] == "4.99"


def test_deprecated_qt6_flag_is_absent():
    # supportsQt6 は QGIS 4.0 正式版で無効化された。qgisMaximumVersion で代替する。
    assert "supportsQt6" not in load_metadata()


def test_version_matches_pyproject():
    # リリース時は metadata.txt と pyproject.toml の両方を手で更新する。
    # Python 3.9 には tomllib がないため version 行を正規表現で読む。
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    assert match is not None
    assert load_metadata()["version"] == match.group(1)
```

- [ ] **Step 2: テストが失敗することを確認する**

Run:

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py -q
```

Expected: `1 failed, 2 passed`。失敗は `test_version_matches_pyproject` で、`assert 'dev' == '0.1.0'` の形。

- [ ] **Step 3: metadata.txt を全文書き換える**

`metadata.txt` を次の内容で上書きする（UTF-8、改行 LF）。

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

- [ ] **Step 4: テストが通ることを確認する**

Run:

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py -q
```

Expected: `3 passed`。

- [ ] **Step 5: QGIS が読む主要キーを目視で確認する**

Run:

```bash
.venv/bin/python - <<'PY'
import configparser
p = configparser.ConfigParser()
p.read("metadata.txt", encoding="utf-8")
g = p["general"]
for k in ("name", "version", "author", "email", "category", "experimental", "hasProcessingProvider", "icon", "repository", "tracker", "homepage"):
    print(f"{k}={g[k]}")
print("supportsQt6" in g, "plugin_dependencies" in g)
PY
```

Expected: 各キーが Global Constraints の値で表示され、最終行が `False False`。

- [ ] **Step 6: Ruff を通す**

Run:

```bash
.venv/bin/ruff check tests/test_metadata.py && .venv/bin/ruff format --check tests/test_metadata.py
```

Expected: `All checks passed!` と `1 file already formatted`。

- [ ] **Step 7: コミットする**

```bash
git add metadata.txt tests/test_metadata.py
git commit -m "$(cat <<'MSG'
chore: metadata.txt をプラグインの実態に合わせる

表示名を 国土数値情報ブラウザ にし、説明・作者・URL・分類を埋める。
version は pyproject.toml と同じ 0.1.0 にし、一致をテストで固定する。
書式は MIERUNE/GTFS-GO の metadata.txt に倣う。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QAxRr2rTyYHn1s7hzJt48Y
MSG
)"
```

---

### Task 2: pyproject.toml の書き換えと uv.lock の再生成

**Files:**
- Modify: `pyproject.toml`（全文置換）
- Modify: `uv.lock`（`uv lock` で再生成。手で編集しない）
- Modify: `requirements-test.txt:1-2`（コメント 1 行追加）

**Interfaces:**
- Consumes: Task 1 の `metadata.txt` の `version=0.1.0`、`tests/test_metadata.py::test_version_matches_pyproject`（`version = "..."` 行を読む）
- Produces: `pyproject.toml` の `[project] name = "ksj-browser"`、`version = "0.1.0"`。`uv.lock` の仮想プロジェクト項目 `name = "ksj-browser"`

- [ ] **Step 1: pyproject.toml を全文書き換える**

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

- [ ] **Step 2: requirements-test.txt に相互参照コメントを足す**

現在の先頭 2 行のコメントの直後（3 行目）に次の 1 行を挿入する。固定値の行は変えない。

```
# pyproject.toml の [dependency-groups] dev と同じ固定にする。片方を変えたらもう片方も変える。
```

結果は次のとおり。

```
# テスト実行に必要な依存。scripts/test-docker.sh（コンテナ内）と README のホスト手順で共有する。
# pytest-qgis 3 以降は Python 3.10 以上が必要なため、QGIS 付属 Python が 3.9 のホストでは 2.1.0 に固定する。
# pyproject.toml の [dependency-groups] dev と同じ固定にする。片方を変えたらもう片方も変える。
pytest>=8,<10
pytest-cov==7.1.0
pytest-qgis==2.1.0; python_version < "3.10"
pytest-qgis==5.0.2; python_version >= "3.10"
```

- [ ] **Step 3: uv.lock を再生成する**

ネットワークを使う（`pytest-cov 7.1.0` と `pytest-qgis 5.0.2` の情報取得）。

Run:

```bash
uv lock
```

Expected: `Resolved N packages in …` と表示され、`uv.lock` が更新される。

- [ ] **Step 4: ロックの内容を確認する**

Run:

```bash
grep -c 'qgis-plugin-template' uv.lock; grep -n 'name = "ksj-browser"' uv.lock; grep -n 'name = "pytest-cov"' uv.lock; grep -n 'name = "pytest-qgis"' uv.lock; uv lock --check
```

Expected: 1 行目は `0`。`ksj-browser` と `pytest-cov` が各 1 件以上、`pytest-qgis` が 2 件（2.1.0 と 5.0.2）。`uv lock --check` はエラーなしで終わる。

- [ ] **Step 5: CI と同じ手順で同期する**

Run:

```bash
uv sync --locked
```

Expected: `Installed …` / `Uninstalled …` の行が出て終了コード 0。`pytest-cov` が 7.1.0 で入る。

- [ ] **Step 6: 仮想環境が作り直されていないことと QGIS が読めることを確認する**

Run:

```bash
grep include-system-site-packages .venv/pyvenv.cfg
.venv/bin/python -m pip show pytest-cov | head -2
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -c "from qgis.core import Qgis; print(Qgis.QGIS_VERSION)"
```

Expected: `include-system-site-packages = true`、`Version: 7.1.0`、QGIS のバージョン文字列（例 `3.44.x`）。

もし `include-system-site-packages` が `false` になっていたり QGIS が import できなければ、`uv sync` が仮想環境を作り直している。README の手順で作り直してから Step 5 をやり直す。

```bash
rm -rf .venv
uv venv --python /Applications/QGIS.app/Contents/MacOS/bin/python3 --system-site-packages
uv sync --locked
```

- [ ] **Step 7: Ruff とテストを通す**

Run:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py -q
```

Expected: Ruff は `All checks passed!` と `N files already formatted`。pytest は `3 passed`。

- [ ] **Step 8: 差分が意図どおりか確認してコミットする**

Run:

```bash
git status --short
git diff --stat
```

Expected: 変更は `pyproject.toml`、`uv.lock`、`requirements-test.txt` の 3 ファイルだけ。

```bash
git add pyproject.toml uv.lock requirements-test.txt
git commit -m "$(cat <<'MSG'
chore: pyproject.toml を実態に合わせ uv.lock を再生成

プロジェクト名を ksj-browser にし、実行時依存を空にする。
dev グループは requirements-test.txt と同じ固定（pytest-cov と
Python バージョン別の pytest-qgis）に揃え、uv sync で消えないようにする。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QAxRr2rTyYHn1s7hzJt48Y
MSG
)"
```

---

### Task 3: 識別子 ksj-browser への統一と表示名定数

**Files:**
- Modify: `README.md:1`, `README.md:241`
- Modify: `.github/agents/copilot-instructions.md:1`
- Modify: `.specify/memory/constitution.md:1`
- Modify: `specs/004-complete-catalog/verification.md:9,80,93-96`
- Modify: `specs/004-complete-catalog/review-followups.md:3`
- Modify: `specs/001-update-dosyasaigai-script/tasks.md:99`
- Modify: `specs/003-school-data/quickstart.md:21`
- Modify: `docs/superpowers/plans/2026-10-23-issue-6.md:5`
- Modify: `docs/superpowers/plans/2026-10-24-qgis4-migration.md:412`
- Modify: `docs/superpowers/specs/2026-10-24-qgis4-migration-design.md:103`
- Modify: `plugin.py:8`
- Modify: `ksj/browser.py:16`
- Test: 既存の `tests/test_browser_items.py`、`tests/test_smoke.py`

**Interfaces:**
- Consumes: なし
- Produces: `plugin.PLUGIN_NAME == "国土数値情報ブラウザ"`、`KsjDataItemProvider.name()` が `"国土数値情報ブラウザ"` を返す

- [ ] **Step 1: 置き換え前の件数を記録する**

Run:

```bash
git grep -n ksj-provider -- ':!docs/superpowers/specs/2026-10-26-plugin-metadata-design.md' ':!docs/superpowers/plans/2026-10-26-plugin-metadata.md' | wc -l
```

Expected: `16`（README 2、copilot-instructions 1、constitution 1、verification.md 6、review-followups 1、tasks.md 1、quickstart 1、issue-6 1、qgis4-migration plan 1、qgis4-migration design 1）。

- [ ] **Step 2: 小文字の識別子を一括置換する**

macOS の `sed` なので `-i ''`。大文字小文字を区別するため、残す `KSJ-Provider` には一致しない。

```bash
sed -i '' 's/ksj-provider/ksj-browser/g' \
  README.md \
  .github/agents/copilot-instructions.md \
  .specify/memory/constitution.md \
  specs/004-complete-catalog/verification.md \
  specs/004-complete-catalog/review-followups.md \
  specs/001-update-dosyasaigai-script/tasks.md \
  specs/003-school-data/quickstart.md \
  docs/superpowers/plans/2026-10-23-issue-6.md \
  docs/superpowers/plans/2026-10-24-qgis4-migration.md \
  docs/superpowers/specs/2026-10-24-qgis4-migration-design.md
```

- [ ] **Step 3: README の題名を表示名に合わせる**

Step 2 で 1 行目は `# ksj-browser — 国土数値情報 QGIS プラグイン` になっている。これを次に置き換える。

```markdown
# ksj-browser — 国土数値情報ブラウザ（QGIS プラグイン）
```

```bash
sed -i '' '1s/.*/# ksj-browser — 国土数値情報ブラウザ（QGIS プラグイン）/' README.md
sed -n '1p;241p' README.md
```

Expected: 1 行目が上の題名、241 行目が `cd C:\path\to\ksj-browser`。

- [ ] **Step 4: 表示名の定数を置き換える**

`plugin.py` の 8 行目を次にする。

```python
PLUGIN_NAME = "国土数値情報ブラウザ"
```

`ksj/browser.py` の `KsjDataItemProvider.name()` を次にする。

```python
    def name(self):
        return "国土数値情報ブラウザ"
```

```bash
sed -i '' 's/^PLUGIN_NAME = "KSJ-Provider"$/PLUGIN_NAME = "国土数値情報ブラウザ"/' plugin.py
sed -i '' 's/return "KSJ Provider"$/return "国土数値情報ブラウザ"/' ksj/browser.py
sed -n '8p' plugin.py; sed -n '15,16p' ksj/browser.py
```

Expected: それぞれ上記の行が表示される。

- [ ] **Step 5: 置き換え結果を確認する**

Run:

```bash
git grep -n ksj-provider -- ':!docs/superpowers/specs/2026-10-26-plugin-metadata-design.md' ':!docs/superpowers/plans/2026-10-26-plugin-metadata.md'
echo "--- 残る旧表示名（歴史的記述のみのはず） ---"
git grep -n 'KSJ.Provider' -- ':!docs/superpowers/specs/2026-10-26-plugin-metadata-design.md' ':!docs/superpowers/plans/2026-10-26-plugin-metadata.md'
```

Expected: 1 つ目は出力なし。2 つ目は次の 6 行だけ。

```
docs/superpowers/plans/2026-10-24-qgis4-migration.md:270:name=KSJ-Provider
docs/superpowers/plans/2026-10-24-qgis4-migration.md:273:about=KSJ-Provider Plugin
docs/superpowers/plans/2026-10-24-qgis4-migration.md:417:…KSJ-Provider が一覧に出て…
docs/superpowers/plans/2026-10-24-qgis4-migration.md:851:…KSJ-Provider が有効化できること。
docs/superpowers/specs/2026-10-24-qgis4-migration-design.md:103:…プラグイン管理から KSJ-Provider を有効化できること。
specs/001-zip-recursive-browse/quickstart.md:61:   - QGIS プラグインマネージャーから「KSJ Provider」をインストール
```

`metadata.txt`、`plugin.py`、`ksj/browser.py` が含まれていないこと。

- [ ] **Step 6: Ruff とブラウザ関連テストを通す**

Run:

```bash
.venv/bin/ruff check plugin.py ksj/browser.py && .venv/bin/ruff format --check plugin.py ksj/browser.py
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_browser_items.py tests/test_smoke.py -q
```

Expected: Ruff は `All checks passed!`。pytest は全件 `passed`。

- [ ] **Step 7: コミットする**

```bash
git add README.md .github/agents/copilot-instructions.md .specify/memory/constitution.md \
  specs/004-complete-catalog/verification.md specs/004-complete-catalog/review-followups.md \
  specs/001-update-dosyasaigai-script/tasks.md specs/003-school-data/quickstart.md \
  docs/superpowers/plans/2026-10-23-issue-6.md docs/superpowers/plans/2026-10-24-qgis4-migration.md \
  docs/superpowers/specs/2026-10-24-qgis4-migration-design.md plugin.py ksj/browser.py
git commit -m "$(cat <<'MSG'
chore: 識別子を ksj-browser に統一し表示名を揃える

README 題名・Issue URL・パスの ksj-provider を GitHub リポジトリ名の
ksj-browser に置き換える。plugin.py と ksj/browser.py の表示名を
metadata.txt と同じ 国土数値情報ブラウザ にする。QGIS 4 移行文書に
残る当時の表示名 KSJ-Provider は記録として変えない。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QAxRr2rTyYHn1s7hzJt48Y
MSG
)"
```

---

### Task 4: 最終検証

**Files:**
- 変更なし（検証のみ）

**Interfaces:**
- Consumes: Task 1〜3 のコミット
- Produces: なし

- [ ] **Step 1: ホストで全テストを流す**

Run:

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

Expected: 全件 `passed`（既存のスキップがあればそのまま）。失敗があれば Task 1〜3 の変更が原因か切り分けてから直す。

- [ ] **Step 2: Docker（QGIS 3.44）で metadata テストを流す**

Docker Desktop が起動している場合のみ。起動していなければこの Step は飛ばし、報告に「Docker 未実行のため省略。CI で 3.44 / 4.0 / 4.2 が走る」と書く。

Run:

```bash
bash scripts/test-docker.sh tests/test_metadata.py -q
```

Expected: `3 passed`。

- [ ] **Step 3: ブランチの状態を確認する**

Run:

```bash
git status --short
git log --oneline main..HEAD
```

Expected: 作業ツリーはクリーン。コミットは設計書・実装計画のものと Task 1〜3 の 3 件。

- [ ] **Step 4: ローカル環境の申し送りを報告に含める**

リポジトリ外のため計画では実行しない。報告に次の手順を載せる。

```bash
# 作業ディレクトリの改名（このセッションを終えてから実行する）
mv ~/Documents/GitHub/ksj-provider ~/Documents/GitHub/ksj-browser
# QGIS プロファイルのシンボリックリンクを張り替える（QGIS3 と QGIS4 の両方）
for v in QGIS3 QGIS4; do
  d=~/Library/Application\ Support/QGIS/$v/profiles/default/python/plugins
  rm "$d/ksj-provider"
  ln -s ~/Documents/GitHub/ksj-browser "$d/ksj-browser"
done
```

QGIS はフォルダ名でプラグインを識別するため、張り替え後はプラグイン管理で「国土数値情報ブラウザ」を一度有効化し直す。`.venv/pyvenv.cfg` の `prompt = ksj-provider` はプロンプト表示だけなので放置してよい。
