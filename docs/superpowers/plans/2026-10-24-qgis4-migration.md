# QGIS 4 対応 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** QGIS 3.40 から 4.x までの全バージョンでプラグインが読み込まれ、Processing 画面が開き、公式の Qt6 互換チェッカーの指摘がゼロになる状態を、2 本の Pull Request で作る。

**Architecture:** PR1 は `ksj/processing_widgets.py` に import シムを置いて QGIS 4.2 の `AlgorithmWidget` と 4.0 以前の `AlgorithmDialog` を同じ名前 `AlgorithmWidgetBase` で扱い、`metadata.txt` に `qgisMaximumVersion=4.99` を加えて QGIS 4 がプラグインを読み込めるようにし、CI の QGIS 4.2 ジョブを必須化する。PR2 は `supportsQt6` を削除し、公式チェッカー `pyqgis4-checker` で 26 箇所の enum 修飾を機械的に書き換え、同じチェッカーを Lint ワークフローに追加する。

**Tech Stack:** Python 3.9 以上、QGIS 3.40〜4.2（PyQt5 / PyQt6 を `qgis.PyQt` 経由で利用）、pytest + pytest-qgis、Docker（`qgis/qgis:*` イメージ、`ghcr.io/qgis/pyqgis4-checker:main-ubuntu`）、Ruff 0.14、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-10-24-qgis4-migration-design.md`

## Global Constraints

- Python 3.9 以上で動くこと（`match` 文・`X | Y` 型表記は使わない）。
- QGIS 3.40 以上 4.x まで対応。Qt は必ず `qgis.PyQt` 経由で import する。追加依存は入れない。
- パッケージ内は `from .child import Child` 形式の相対 import（Plugin Reloader 互換のため）。
- コード・コメント・コミットメッセージ・PR 本文・ドキュメントは日本語。コミットは Conventional Commits（`fix:` / `feat:` / `refactor:` / `ci:` / `docs:` / `test:`、要約 50 文字程度）。
- コミットメッセージ末尾に次の 2 行を付ける。

  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_011cFb7D28ykjf9Jk4241kEs
  ```

- PR 本文の末尾に次を付ける。

  ```
  🤖 Generated with [Claude Code](https://claude.com/claude-code)

  https://claude.ai/code/session_011cFb7D28ykjf9Jk4241kEs
  ```

- Processing のアルゴリズム ID・パラメータ名・出力名は変えない。クラス名の変更は内部 API のみ。
- `uv run` は `uv.lock` を書き換えることがあるため、Ruff は `.venv/bin/ruff` を直接使う。もし `uv run` を使ってしまったら `git checkout uv.lock` で戻す。
- PR2 のタスク（Task 5 以降）は PR1 がマージされた後に `main` から分岐して始める。

## 実行メモ

- Docker テストは `bash scripts/test-docker.sh [pytest 引数]` で実行する。`QGIS_TEST_IMAGE` を省略すると `qgis/qgis:3.44`。全件実行は Apple Silicon の AMD64 エミュレーションで 10 分前後かかることがあるので、`run_in_background` で起動して完了通知を待つか、対象ファイルを絞って実行する。
- 各タスクでは対象テストを絞った高速な確認を行い、全バージョン・全件の実行は Task 4（PR1）と Task 9（PR2）でまとめて行う。
- Docker イメージ `qgis/qgis:3.40`・`3.44`・`4.0-trixie`・`4.2-trixie`・`ghcr.io/qgis/pyqgis4-checker:main-ubuntu` はローカルに取得済み。
- 手動確認（QGIS 4.2.2）は利用者が行う。該当ステップでは利用者に手順を提示し、結果の報告を待ってから次へ進む。

## File Structure

### PR1（ブランチ `fix/qgis42-processing-widget`、作成済み・設計書をコミット済み）

| ファイル | 役割と変更 |
| --- | --- |
| `ksj/processing_widgets.py` | Processing 画面の選択 UI。`AlgorithmDialog` の固定 import を `AlgorithmWidgetBase` シムに置き換え、`CatalogAlgorithmDialog` を `CatalogAlgorithmWidget` に改名する。 |
| `ksj/processing_algorithms.py` | アルゴリズム本体。`createCustomParametersWidget` の遅延 import 先を `CatalogAlgorithmWidget` にする。 |
| `tests/test_processing_widgets.py` | 画面のテスト。`finish` の差し替え先を `ksj.processing_widgets.AlgorithmWidgetBase` にし、シムの契約テストを 1 件足す。 |
| `metadata.txt` | プラグイン定義。`qgisMaximumVersion=4.99` を追加する。 |
| `tests/test_metadata.py`（新規） | `metadata.txt` の対応バージョン範囲を検証する。 |
| `.github/workflows/test.yaml` | QGIS 4.2 を通常マトリクスに入れ、experimental の仕組みを削除する。 |
| `README.md`、`AGENTS.md` | CI の説明を「3.40・3.44・4.0・4.2 を必須チェック」に改める。 |

### PR2（ブランチ `feat/qgis4-migration`、PR1 マージ後に `main` から作成）

| ファイル | 役割と変更 |
| --- | --- |
| `metadata.txt` | `supportsQt6=True` を削除する。 |
| `tests/test_metadata.py` | `supportsQt6` が無いことを検証する。 |
| `ksj/browser.py`、`ksj/catalog_browser.py`、`ksj/mesh_index.py`、`ksj/processing_algorithms.py` | enum 修飾（本体 15 箇所）。公式チェッカーで機械的に書き換える。 |
| `tests/test_catalog_browser.py`、`tests/test_lazy_loading.py`、`tests/test_loading_indicator.py`、`tests/test_mesh_index.py` | enum 修飾（テスト 11 箇所）。同上。 |
| `.github/workflows/lint.yaml` | `qt6-check` ジョブを追加する。 |
| `README.md`、`AGENTS.md` | 対応バージョンの明記、Qt6 互換チェックの説明とローカル実行コマンド。 |

---

## PR1: QGIS 4.2 で Processing 画面を開けるようにする（Issue #21）

### Task 1: `AlgorithmWidget` 互換シムとクラス改名

**Files:**
- Modify: `ksj/processing_widgets.py:11-18`（import 群）、`ksj/processing_widgets.py:381`（クラス定義）
- Modify: `ksj/processing_algorithms.py:72-75`
- Test: `tests/test_processing_widgets.py:115-130`

**Interfaces:**
- Consumes: QGIS 4.2 の `processing.gui.algorithm_widget.AlgorithmWidget`、QGIS 4.0 以前の `processing.gui.AlgorithmDialog.AlgorithmDialog`。どちらも `__init__(alg, in_place=False, parent=None, ...)` と `finish(successful, result, context, feedback, in_place=False)` を持つ。
- Produces: `ksj.processing_widgets.AlgorithmWidgetBase`（利用可能な側の QGIS クラス）、`ksj.processing_widgets.CatalogAlgorithmWidget(algorithm, parent=None)`（旧 `CatalogAlgorithmDialog`、`AlgorithmWidgetBase` のサブクラス）。

- [ ] **Step 1: 現状の失敗を QGIS 4.2 で確認する**

Run:

```bash
QGIS_TEST_IMAGE=qgis/qgis:4.2-trixie bash scripts/test-docker.sh tests/test_processing_widgets.py -q
```

Expected: 13 件が `ModuleNotFoundError: No module named 'processing.gui.AlgorithmDialog'` で FAIL（`13 failed` または `13 errors`）。

- [ ] **Step 2: テストをプラグイン側の基底クラス参照に変え、シムの契約テストを足す**

`tests/test_processing_widgets.py` の `test_gui_load_schedules_layer_for_map`（115 行目から）を次に置き換える。変更点は旧モジュールの直接 import をやめ、`AlgorithmWidgetBase` の `finish` を差し替えること。

```python
def test_gui_load_schedules_layer_for_map(dialogs, tmp_path, monkeypatch):
    from qgis.core import QgsProcessingFeedback, QgsProject, QgsVectorLayer

    from ksj.processing_widgets import AlgorithmWidgetBase

    dialog = dialogs("load_layer")
    path = point_file(tmp_path)
    layer = QgsVectorLayer(str(path), "ダム", "ogr")
    context = QgsProcessingContext()
    project = QgsProject()
    context.setProject(project)
    context.temporaryLayerStore().addMapLayer(layer)
    # 標準QGISの結果処理に渡す直前の契約を確認する。
    monkeypatch.setattr(AlgorithmWidgetBase, "finish", lambda *args, **kwargs: None)
    dialog.finish(True, {"OUTPUT": layer.id()}, context, QgsProcessingFeedback())
    assert context.willLoadLayerOnCompletion(layer.id())
    assert context.layerToLoadOnCompletionDetails(layer.id()).project is project
```

続けて、ファイル末尾（`test_sublayer_restore_and_raster_provider` の後）に次のテストを追加する。

```python
def test_custom_widget_subclasses_available_processing_base(dialogs):
    """QGIS 4.2 の AlgorithmWidget と 4.0 以前の AlgorithmDialog のどちらでも画面を作れる。"""
    from ksj.processing_widgets import AlgorithmWidgetBase, CatalogAlgorithmWidget

    dialog = dialogs("search_datasets")
    assert isinstance(dialog, CatalogAlgorithmWidget)
    assert isinstance(dialog, AlgorithmWidgetBase)
    assert AlgorithmWidgetBase.__module__ in {
        "processing.gui.algorithm_widget",
        "processing.gui.AlgorithmDialog",
    }
```

- [ ] **Step 3: テストが失敗することを QGIS 3.44 で確認する**

Run:

```bash
bash scripts/test-docker.sh tests/test_processing_widgets.py -q
```

Expected: `test_gui_load_schedules_layer_for_map` と `test_custom_widget_subclasses_available_processing_base` の 2 件が `ImportError: cannot import name 'AlgorithmWidgetBase'` で FAIL、他は PASS。

- [ ] **Step 4: import シムとクラス改名を実装する**

`ksj/processing_widgets.py` の 11〜18 行目を次に置き換える（`AlgorithmDialog` の固定 import を削除し、相対 import の後にシムを置く）。

```python
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QComboBox, QCompleter, QFormLayout, QLabel, QWidget
from processing.gui.wrappers import WidgetWrapper

from . import catalog, local_storage, zip_scanner
from .processing_algorithms import scan_layers

try:
    # QGIS 4.2 以降は AlgorithmDialog が AlgorithmWidget（QWidget 基底）に改名された。
    from processing.gui.algorithm_widget import AlgorithmWidget as AlgorithmWidgetBase
except ImportError:
    from processing.gui.AlgorithmDialog import AlgorithmDialog as AlgorithmWidgetBase
```

同ファイルの `class CatalogAlgorithmDialog(AlgorithmDialog):` の行（編集前 381 行目、上記の追加後は 386 行目）を次に変える（`__init__` と `finish` の中身は変更しない）。

```python
class CatalogAlgorithmWidget(AlgorithmWidgetBase):
```

`ksj/processing_algorithms.py` の 72〜75 行目を次に変える。

```python
    def createCustomParametersWidget(self, parent=None):
        from .processing_widgets import CatalogAlgorithmWidget

        return CatalogAlgorithmWidget(self, parent=parent)
```

- [ ] **Step 5: テストが通ることを QGIS 3.44 と 4.2 で確認する**

Run:

```bash
bash scripts/test-docker.sh tests/test_processing_widgets.py tests/test_processing.py -q
QGIS_TEST_IMAGE=qgis/qgis:4.2-trixie bash scripts/test-docker.sh tests/test_processing_widgets.py tests/test_processing.py -q
```

Expected: どちらも全件 PASS（3.44 は 40 件、4.2 も 40 件。以前 4.2 で失敗していた 13 件と新規 1 件を含む）。

- [ ] **Step 6: Ruff を通す**

Run:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Expected: `All checks passed!` と `N files already formatted`。フォーマット差分が出たら `.venv/bin/ruff format .` を実行して再確認する。

- [ ] **Step 7: コミット**

```bash
git add ksj/processing_widgets.py ksj/processing_algorithms.py tests/test_processing_widgets.py
git commit -F - <<'EOF'
fix: QGIS 4.2 の AlgorithmWidget 改名に対応

processing.gui.algorithm_widget.AlgorithmWidget を優先し、無ければ従来の
AlgorithmDialog を使う import シムを置き、画面クラスを CatalogAlgorithmWidget
に改名した。テストはプラグイン側の基底クラスを参照する。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011cFb7D28ykjf9Jk4241kEs
EOF
```

---

### Task 2: `qgisMaximumVersion` の追加と metadata の検証テスト

**Files:**
- Modify: `metadata.txt:3`
- Create: `tests/test_metadata.py`

**Interfaces:**
- Produces: `tests/test_metadata.py::load_metadata() -> configparser.SectionProxy`（`[general]` セクション）。Task 5 で `supportsQt6` の検証を追加する。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_metadata.py` を新規作成する。

```python
"""metadata.txt が QGIS 3.40 から 4.x までの読み込み条件を満たすこと。"""

import configparser
from pathlib import Path

METADATA = Path(__file__).resolve().parents[1] / "metadata.txt"


def load_metadata():
    parser = configparser.ConfigParser()
    parser.read(METADATA, encoding="utf-8")
    return parser["general"]


def test_version_range_covers_qgis_3_and_4():
    general = load_metadata()
    assert general["qgisMinimumVersion"] == "3.40"
    # qgisMaximumVersion が無いと QGIS 4 は上限を 3.99 とみなして読み込まない。
    assert general["qgisMaximumVersion"] == "4.99"
```

- [ ] **Step 2: テストが失敗することを確認する**

Run:

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py -q
```

Expected: `KeyError: 'qgisMaximumVersion'` で 1 件 FAIL。（ホストの `.venv` が無い、または QGIS 付属 Python でない場合は `bash scripts/test-docker.sh tests/test_metadata.py -q` を使う。）

- [ ] **Step 3: metadata.txt に上限バージョンを追加する**

`metadata.txt` の 3 行目 `qgisMinimumVersion=3.40` の直後に 1 行追加し、先頭 5 行を次の形にする。

```
[general]
name=KSJ-Provider
qgisMinimumVersion=3.40
qgisMaximumVersion=4.99
about=KSJ-Provider Plugin
```

- [ ] **Step 4: テストが通ることを確認する**

Run:

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py -q
```

Expected: `1 passed`。

- [ ] **Step 5: コミット**

```bash
git add metadata.txt tests/test_metadata.py
git commit -F - <<'EOF'
fix: QGIS 4 で読み込めるよう qgisMaximumVersion を追加

qgisMaximumVersion が無いと QGIS 4 は上限を 3.99 とみなしてプラグインを
非互換と判定する。4.99 を指定し、metadata の検証テストを追加した。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011cFb7D28ykjf9Jk4241kEs
EOF
```

---

### Task 3: CI の QGIS 4.2 を必須化し、ドキュメントを更新する

**Files:**
- Modify: `.github/workflows/test.yaml:17-32`
- Modify: `README.md:177`
- Modify: `AGENTS.md:7`

**Interfaces:**
- Produces: ジョブ名 `QGIS <version>`（例 `QGIS 4.2-trixie`）。ブランチ保護の必須チェック名を更新する場合はこの名前を使う。

- [ ] **Step 1: ワークフローから experimental の仕組みを外す**

`.github/workflows/test.yaml` の `jobs:` 以下 17〜32 行目を次に置き換える（`env:` 以降は変更しない）。

```yaml
  test:
    name: QGIS ${{ matrix.qgis }}
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        qgis: ["3.40", "3.44", "4.0-trixie", "4.2-trixie"]
```

- [ ] **Step 2: YAML として読めることを確認する**

Run:

```bash
ruby -ryaml -e 'y = YAML.load_file(".github/workflows/test.yaml"); p y["jobs"]["test"]["strategy"]["matrix"]["qgis"]; p y["jobs"]["test"].key?("continue-on-error")'
```

Expected: `["3.40", "3.44", "4.0-trixie", "4.2-trixie"]` と `false`。

- [ ] **Step 3: README と AGENTS.md の CI 説明を更新する**

`README.md` 177 行目の段落を次に置き換える。

```
GitHub Actions でも同じスクリプトを使い、QGIS 3.40（最低対応版）・3.44・4.0・4.2 のテストとカバレッジを実行し、各バージョンの `coverage.xml` を成果物として保存します。別のジョブで Ruff の lint・format を確認します。Pull Request、`main` への push、Actions 画面からの手動実行に対応しています。Actions のバージョン更新は Dependabot が月次で提案します。
```

`AGENTS.md` 7 行目の文 `GitHub Actions は同じスクリプトで QGIS 3.40・3.44・4.0 を確認し、QGIS 4.2 は実験的ジョブ（失敗を許容）として結果を記録します。` を次に置き換える（段落の他の文は変えない）。

```
GitHub Actions は同じスクリプトで QGIS 3.40・3.44・4.0・4.2 を確認します。
```

- [ ] **Step 4: 「実験的」の記述が残っていないことを確認する**

Run:

```bash
grep -rn "実験的\|experimental" README.md AGENTS.md .github/workflows/test.yaml
```

Expected: 出力なし。

- [ ] **Step 5: コミット**

```bash
git add .github/workflows/test.yaml README.md AGENTS.md
git commit -F - <<'EOF'
ci: QGIS 4.2 のテストを必須チェックに昇格

Processing 画面の 4.2 対応が入ったため、実験的ジョブの仕組みを外して
4.2 を通常のマトリクスに加えた。README と AGENTS.md の説明も更新した。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011cFb7D28ykjf9Jk4241kEs
EOF
```

---

### Task 4: PR1 の総合検証と Pull Request 作成

**Files:**
- 変更なし（検証と PR 作成のみ）

- [ ] **Step 1: 4 バージョンで全テストを実行する**

Run（各コマンドは数分かかる。バックグラウンドで順に実行し、完了通知を待つ）:

```bash
for image in qgis/qgis:3.40 qgis/qgis:3.44 qgis/qgis:4.0-trixie qgis/qgis:4.2-trixie; do
  echo "==== $image"
  QGIS_TEST_IMAGE=$image bash scripts/test-docker.sh -q 2>&1 | tail -3
done
```

Expected: 4 回とも `240 passed`（既存 238 件 + `test_custom_widget_subclasses_available_processing_base` + `test_version_range_covers_qgis_3_and_4`）。`failed`・`error` が 0 件であることが条件。失敗があれば原因を直してから先へ進む。

- [ ] **Step 2: Ruff と作業ツリーを確認する**

Run:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && git status --short
```

Expected: Ruff が通り、未コミットの変更がない（`coverage.xml` と `.coverage` は `.gitignore` 済み）。

- [ ] **Step 3: 利用者に QGIS 4.2.2 での手動確認を依頼する**

次の手順を利用者に提示し、結果の報告を待つ。報告を得るまで PR のマージには進まない。

```bash
ln -s "$(pwd)" ~/Library/Application\ Support/QGIS/QGIS4/profiles/default/python/plugins/ksj-browser
open /Applications/QGIS-final-4_2_2.app
```

確認項目:
1. プラグイン管理で KSJ-Provider が一覧に出て、有効化できること（`qgisMaximumVersion` が効いている）。
2. Processing ツールボックスの「国土数値情報（KSJ）」配下の 4 アルゴリズム（データセット検索・配布一覧・配布ファイルのダウンロード・レイヤー読み込み）の画面が例外なく開くこと。
3. 配布一覧の画面でデータセットを選ぶと、年度・地域の候補が連動して絞り込まれること。
4. レイヤー読み込みを実行すると地図にレイヤーが追加されること。

- [ ] **Step 4: ブランチを push して PR を作る**

Run:

```bash
git push -u origin fix/qgis42-processing-widget
gh pr create --base main --title "fix: QGIS 4.2 の AlgorithmWidget 改名に対応し 4.2 を必須チェックに昇格" --body-file - <<'EOF'
## 概要

QGIS 4.2 で `processing.gui.AlgorithmDialog` が `processing.gui.algorithm_widget.AlgorithmWidget` に改名され、Processing 画面が開けなくなっていた問題を修正します。

- `ksj/processing_widgets.py`: 新モジュールを優先し、無ければ旧モジュールを使う import シム（`AlgorithmWidgetBase`）。画面クラスを `CatalogAlgorithmWidget` に改名。
- `metadata.txt`: `qgisMaximumVersion=4.99` を追加。これが無いと QGIS 4 は上限を 3.99 とみなしてプラグインを読み込みません。
- `.github/workflows/test.yaml`: QGIS 4.2 を通常のマトリクスに加え、実験的ジョブの仕組みを削除。
- README・AGENTS.md の CI 説明を更新。

Closes #21

## テスト

- `bash scripts/test-docker.sh -q` を `qgis/qgis:3.40`・`3.44`・`4.0-trixie`・`4.2-trixie` で実行し、各 240 件成功。
- `.venv/bin/ruff check .`・`.venv/bin/ruff format --check .` 成功。
- QGIS 4.2.2（macOS）で手動確認: プラグイン有効化、4 アルゴリズムの画面表示、データセット連動の絞り込み、レイヤー読み込みの地図追加。

## 関連

- 設計書: `docs/superpowers/specs/2026-10-24-qgis4-migration-design.md`
- 後続: Issue #22（移行ガイドの残り: `supportsQt6` 削除、enum 修飾、pyqgis4-checker の CI 追加）

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_011cFb7D28ykjf9Jk4241kEs
EOF
```

Expected: PR の URL が表示される。手動確認の結果が本文と異なる場合は本文を修正する。

- [ ] **Step 5: CI の完了を確認し、利用者にマージを依頼する**

Run:

```bash
gh pr checks --watch
```

Expected: `QGIS 3.40`・`QGIS 3.44`・`QGIS 4.0-trixie`・`QGIS 4.2-trixie`・`Ruff` の 5 チェックが成功。マージは利用者が行う。マージ後に Task 5 へ進む。

---

## PR2: QGIS 4 移行ガイドの完了（Issue #22）

### Task 5: PR2 ブランチの作成と `supportsQt6` の削除

**Files:**
- Modify: `metadata.txt:9`（PR1 適用後は 10 行目）
- Modify: `tests/test_metadata.py`

**Interfaces:**
- Consumes: Task 2 の `tests/test_metadata.py::load_metadata()`。

- [ ] **Step 1: PR1 マージ後の main からブランチを切る**

Run:

```bash
git checkout main && git pull --ff-only origin main
git log --oneline -1
git checkout -b feat/qgis4-migration
```

Expected: 直近のコミットが PR1 のマージコミットで、`metadata.txt` に `qgisMaximumVersion=4.99` がある（`grep qgisMaximumVersion metadata.txt` で確認）。

- [ ] **Step 2: 失敗するテストを足す**

`tests/test_metadata.py` の末尾に追加する。

```python
def test_deprecated_qt6_flag_is_absent():
    # supportsQt6 は QGIS 4.0 正式版で無効化された。qgisMaximumVersion で代替する。
    assert "supportsQt6" not in load_metadata()
```

- [ ] **Step 3: テストが失敗することを確認する**

Run:

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py -q
```

Expected: `test_deprecated_qt6_flag_is_absent` が FAIL、`test_version_range_covers_qgis_3_and_4` は PASS。

- [ ] **Step 4: `supportsQt6=True` の行を削除する**

`metadata.txt` から `supportsQt6=True` の行を削除する。該当部分は次の形になる。

```
version=dev

hasProcessingProvider=yes
```

- [ ] **Step 5: テストが通ることを確認する**

Run:

```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py -q
```

Expected: `2 passed`。

- [ ] **Step 6: コミット**

```bash
git add metadata.txt tests/test_metadata.py
git commit -F - <<'EOF'
feat: 無効化済みの supportsQt6 フラグを削除

QGIS 4.0 正式版で supportsQt6 は無視されるようになった。
qgisMaximumVersion=4.99 が QGIS 4 対応の宣言になる。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011cFb7D28ykjf9Jk4241kEs
EOF
```

---

### Task 6: 公式チェッカーで enum 修飾を書き換える

**Files:**
- Modify: `ksj/browser.py:19`、`ksj/catalog_browser.py`（52, 55, 102, 110, 292, 298, 308, 316, 412, 416 行目）、`ksj/mesh_index.py:142`、`ksj/processing_algorithms.py`（109, 119, 295 行目）
- Modify: `tests/test_catalog_browser.py`（183, 197, 199, 207 行目）、`tests/test_lazy_loading.py:212`、`tests/test_loading_indicator.py`（94, 129, 153, 215 行目）、`tests/test_mesh_index.py`（210, 234 行目）
- Test: 既存テスト（挙動は変えない）

**Interfaces:**
- Consumes: `ghcr.io/qgis/pyqgis4-checker:main-ubuntu` の `pyqt5_to_pyqt6.py`。引数は走査するディレクトリ 1 つ。`--dry_run` なしではファイルを書き換え、書き換えが 1 件でもあれば終了コード 1 を返す。
- Produces: 修飾付き enum。`QgsDataItem.Type.Custom` / `QgsDataItem.Type.Error` / `QgsDataItem.State.Populated` / `QgsDataProvider.DataCapability.Net` / `QgsProcessingParameterNumber.Type.Integer` / `QgsProcessingParameterFile.Behavior.Folder` / `QgsAction.ActionType.GenericPython`。

- [ ] **Step 1: 書き換え前の指摘数を記録する**

Run:

```bash
docker run --rm --pull always --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --workdir /workspace/ -v "$(pwd):/workspace/" \
  ghcr.io/qgis/pyqgis4-checker:main-ubuntu \
  pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log .
grep -c ' - ' pyqt6_checker.log
```

Expected: 終了コード 0、指摘 26 件。`pyqt6_checker.log` は `.gitignore` の `*.log` で無視される。

- [ ] **Step 2: チェッカーに書き換えさせる**

Run:

```bash
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --workdir /workspace/ -v "$(pwd):/workspace/" \
  ghcr.io/qgis/pyqgis4-checker:main-ubuntu \
  pyqt5_to_pyqt6.py --logfile /workspace/pyqt6_checker.log .
echo "exit=$?"
git diff --stat
```

Expected: 終了コード 1（書き換えあり）。`git diff --stat` に次の 8 ファイルだけが出る: `ksj/browser.py`、`ksj/catalog_browser.py`、`ksj/mesh_index.py`、`ksj/processing_algorithms.py`、`tests/test_catalog_browser.py`、`tests/test_lazy_loading.py`、`tests/test_loading_indicator.py`、`tests/test_mesh_index.py`。他のファイルが変わっていたら `git diff <file>` で内容を確認し、enum 修飾以外の変更なら `git checkout -- <file>` で戻す。

- [ ] **Step 3: 差分を目で確認する**

Run:

```bash
git diff -U0 | grep '^[-+]' | grep -v '^[-+][-+]'
```

Expected: 変更行は全て「`.Type.`・`.State.`・`.DataCapability.`・`.Behavior.`・`.ActionType.` の挿入」だけで、26 組の `-`/`+` 行。例:

```
-        item = QgsDataItem(QgsDataItem.Custom, parent, text, path)
+        item = QgsDataItem(QgsDataItem.Type.Custom, parent, text, path)
-    return QgsDataProvider.Net
+    return QgsDataProvider.DataCapability.Net
-                type=QgsProcessingParameterNumber.Integer,
+                type=QgsProcessingParameterNumber.Type.Integer,
```

- [ ] **Step 4: フォーマットを整え、指摘がゼロになったことを確認する**

Run:

```bash
.venv/bin/ruff format . && .venv/bin/ruff check .
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --workdir /workspace/ -v "$(pwd):/workspace/" \
  ghcr.io/qgis/pyqgis4-checker:main-ubuntu \
  pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log .
grep -c ' - ' pyqt6_checker.log
```

Expected: Ruff が通り、指摘 0 件（`grep -c` は `0` を出して終了コード 1 を返す）。

- [ ] **Step 5: 影響するテストを QGIS 3.40 と 4.2 で実行する**

Run:

```bash
QGIS_TEST_IMAGE=qgis/qgis:3.40 bash scripts/test-docker.sh tests/test_catalog_browser.py tests/test_lazy_loading.py tests/test_loading_indicator.py tests/test_mesh_index.py tests/test_processing.py tests/test_browser_items.py -q
QGIS_TEST_IMAGE=qgis/qgis:4.2-trixie bash scripts/test-docker.sh tests/test_catalog_browser.py tests/test_lazy_loading.py tests/test_loading_indicator.py tests/test_mesh_index.py tests/test_processing.py tests/test_browser_items.py -q
```

Expected: どちらも全件 PASS（最低対応版の 3.40 でも修飾付き enum が解決することの確認）。

- [ ] **Step 6: コミット**

```bash
git add ksj tests
git commit -F - <<'EOF'
refactor: QGIS の enum を修飾付きの表記に統一

pyqgis4-checker の指摘 26 箇所を公式スクリプトで書き換えた。
QgsDataItem.Custom → QgsDataItem.Type.Custom などで、QGIS 3.40 と 4.2 の
両方で同じ enum オブジェクトに解決する。挙動は変えない。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011cFb7D28ykjf9Jk4241kEs
EOF
```

---

### Task 7: Lint ワークフローに pyqgis4-checker を追加する

**Files:**
- Modify: `.github/workflows/lint.yaml`（`jobs:` の末尾に追加）

**Interfaces:**
- Produces: ジョブ名 `PyQGIS 4 Checker`。失敗時は成果物 `pyqgis4-checker-report`（`pyqt6_checker.log`）。

- [ ] **Step 1: ジョブを追加する**

`.github/workflows/lint.yaml` の末尾（`lint` ジョブの `run: uv run --no-sync ruff format --check --diff .` の後）に次を追加する。

```yaml

  qt6-check:
    name: PyQGIS 4 Checker
    runs-on: ubuntu-latest
    timeout-minutes: 15
    # 公式の移行チェッカー。main-ubuntu は QGIS に追従する移動タグで、Dependabot の管理外。
    container:
      image: ghcr.io/qgis/pyqgis4-checker:main-ubuntu
    steps:
      - uses: actions/checkout@v7
      - name: Qt6 互換をチェック
        run: |
          # 1 回目でレポートを作り、2 回目は書き換えが生じたかを終了コードで判定する。
          # 2 回目はワークスペース内のファイルを書き換えるが、CI のワークスペースは使い捨て。
          pyqt5_to_pyqt6.py --dry_run --logfile pyqt6_checker.log .
          pyqt5_to_pyqt6.py .
      - name: チェック結果を保存
        if: ${{ failure() }}
        uses: actions/upload-artifact@v7
        with:
          name: pyqgis4-checker-report
          path: pyqt6_checker.log
          retention-days: 7
```

- [ ] **Step 2: YAML として読めることを確認する**

Run:

```bash
ruby -ryaml -e 'y = YAML.load_file(".github/workflows/lint.yaml"); p y["jobs"].keys; p y["jobs"]["qt6-check"]["container"]["image"]'
```

Expected: `["lint", "qt6-check"]` と `"ghcr.io/qgis/pyqgis4-checker:main-ubuntu"`。

- [ ] **Step 3: CI と同じ 2 コマンドをローカルの同じイメージで再現する**

Run:

```bash
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --workdir /workspace/ -v "$(pwd):/workspace/" \
  ghcr.io/qgis/pyqgis4-checker:main-ubuntu \
  sh -ec 'pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log . && pyqt5_to_pyqt6.py .'
echo "exit=$?"; git status --short
```

Expected: 終了コード 0 で、作業ツリーに変更がない（Task 6 で全て直っているため 2 回目も書き換えなし）。

- [ ] **Step 4: コミット**

```bash
git add .github/workflows/lint.yaml
git commit -F - <<'EOF'
ci: pyqgis4-checker による Qt6 互換チェックを追加

公式イメージ ghcr.io/qgis/pyqgis4-checker:main-ubuntu で
pyqt5_to_pyqt6.py を実行し、修飾漏れの enum などを検出する。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011cFb7D28ykjf9Jk4241kEs
EOF
```

---

### Task 8: README と AGENTS.md に対応バージョンと Qt6 チェックを記載する

**Files:**
- Modify: `README.md:5`（対応バージョンの明記）、`README.md:177`（CI 説明）、`README.md:179-185`（「ローカルで lint」の直後に節を追加）、`README.md:189`（metadata の参照先）
- Modify: `AGENTS.md:7`

- [ ] **Step 1: README の冒頭に対応バージョンを明記する**

`README.md` 5 行目 `Processingツールボックスから、データを検索・取得し、地図表示や解析に利用できます。` の直後に空行を挟んで次の段落を追加する。

```
QGIS 3.40 以上 4.x まで（Qt 5・Qt 6 の両方）に対応します。
```

- [ ] **Step 2: CI の説明に Qt6 チェックを加える**

`README.md` の CI 説明段落（PR1 で更新した 177 行目付近）の文 `別のジョブで Ruff の lint・format を確認します。` を次に置き換える。

```
別のジョブで Ruff の lint・format と、公式の pyqgis4-checker による Qt6 互換チェックを確認します。
```

- [ ] **Step 3: ローカルでの Qt6 チェック手順を追加する**

`README.md` の「### ローカルで lint」のコードブロックの直後、「### QGIS をインストールした環境でテスト」の前に次の節を追加する。

````
### Qt6 互換チェック

公式の [pyqgis4-checker](https://github.com/qgis/pyqgis4-checker) で、PyQt6 / QGIS 4 で動かない書き方（修飾のない enum など）を検出します。CI の Lint ワークフローと同じイメージ・同じスクリプトです。

```bash
docker run --rm --pull always --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --workdir /workspace/ -v "$(pwd):/workspace/" \
  ghcr.io/qgis/pyqgis4-checker:main-ubuntu \
  pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log .
```

指摘は `pyqt6_checker.log`（`.gitignore` 済み）に書き出されます。`--dry_run` を外すとファイルを直接書き換えるので、コミット済みの状態で実行して差分を確認してください。イメージのタグ `main-ubuntu` は QGIS の更新に追従する移動タグで、Dependabot の管理対象外です。
````

- [ ] **Step 4: metadata の参照文を更新する**

`README.md` の文 `プラグインの最低QGISバージョンは [`metadata.txt`](metadata.txt) を参照してください。` を次に置き換える。

```
プラグインの対応 QGIS バージョン（`qgisMinimumVersion`・`qgisMaximumVersion`）は [`metadata.txt`](metadata.txt) を参照してください。
```

- [ ] **Step 5: AGENTS.md に Qt6 チェックを追記する**

`AGENTS.md` 7 行目の末尾の文 `Lint は `uv sync --locked` の後、`uv run --no-sync ruff check .` と `uv run --no-sync ruff format --check .` を実行します。` の直後に次の文を追加する。

```
Qt6 互換は README の「Qt6 互換チェック」のコマンド（`ghcr.io/qgis/pyqgis4-checker:main-ubuntu` の `pyqt5_to_pyqt6.py --dry_run`）で確認し、CI の Lint ワークフローでも同じチェックを行います。対応バージョンは QGIS 3.40 以上 4.x までで、`metadata.txt` の `qgisMinimumVersion`・`qgisMaximumVersion` で宣言します。
```

- [ ] **Step 6: 記述を確認する**

Run:

```bash
grep -n "4.x まで\|pyqgis4-checker\|qgisMaximumVersion" README.md AGENTS.md
```

Expected: README に冒頭の対応バージョン、CI 説明、Qt6 互換チェック節、metadata 参照文の各行、AGENTS.md に追記した行が出る。

- [ ] **Step 7: コミット**

```bash
git add README.md AGENTS.md
git commit -F - <<'EOF'
docs: QGIS 4 対応の範囲と Qt6 互換チェックの手順を記載

対応バージョンを QGIS 3.40 以上 4.x までと明記し、pyqgis4-checker を
ローカルで実行する手順と CI での扱いを README・AGENTS.md に加えた。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011cFb7D28ykjf9Jk4241kEs
EOF
```

---

### Task 9: PR2 の総合検証と Pull Request 作成

**Files:**
- 変更なし（検証と PR 作成のみ）

- [ ] **Step 1: チェッカー・Ruff・4 バージョンの全テストを実行する**

Run:

```bash
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --workdir /workspace/ -v "$(pwd):/workspace/" \
  ghcr.io/qgis/pyqgis4-checker:main-ubuntu \
  pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log .
grep -c ' - ' pyqt6_checker.log
.venv/bin/ruff check . && .venv/bin/ruff format --check .
for image in qgis/qgis:3.40 qgis/qgis:3.44 qgis/qgis:4.0-trixie qgis/qgis:4.2-trixie; do
  echo "==== $image"
  QGIS_TEST_IMAGE=$image bash scripts/test-docker.sh -q 2>&1 | tail -3
done
git status --short
```

Expected: 指摘 0 件、Ruff 成功、4 回とも `241 passed`（PR1 の 240 件 + `test_deprecated_qt6_flag_is_absent`）、未コミットの変更なし。

- [ ] **Step 2: 利用者に QGIS 4.2.2 での手動確認を依頼する**

次を利用者に提示し、結果の報告を待つ（Task 4 でシンボリックリンクは作成済み）。

```bash
open /Applications/QGIS-final-4_2_2.app
```

確認項目:
1. `supportsQt6` 削除後もプラグイン管理で KSJ-Provider が有効化できること。
2. ブラウザパネルで「国土数値情報」のツリーを展開し、分類・データセットの項目が表示されること（`QgsDataItem.Type.Custom` の経路）。
3. データセットの右クリックで「追加方法・保存先を設定…」などの項目が表示されること（`QAction` の経路）。
4. ブラウザの「メッシュ索引」からメッシュ索引レイヤーを追加し、レイヤープロパティの「アクション」に「このメッシュのデータを追加」が登録されていること（`QgsAction.ActionType.GenericPython` の経路）。

- [ ] **Step 3: ブランチを push して PR を作る**

Run:

```bash
git push -u origin feat/qgis4-migration
gh pr create --base main --title "feat: QGIS 4 移行ガイドに沿って supportsQt6 を削除し enum 修飾と Qt6 チェックを追加" --body-file - <<'EOF'
## 概要

公式の [QGIS 4 移行ガイド](https://plugins.qgis.org/docs/migrate-qgis4) の残り項目を適用します（`qgisMaximumVersion=4.99` は #21 の PR で追加済み）。

- `metadata.txt`: QGIS 4.0 正式版で無効化された `supportsQt6=True` を削除。
- enum 修飾: pyqgis4-checker の指摘 26 箇所（本体 15・テスト 11）を公式スクリプトで `QgsDataItem.Type.Custom` などの修飾付き表記に書き換え。QGIS 3.40 と 4.2 で同じ enum オブジェクトに解決することを確認済みで、挙動は変わりません。
- `.github/workflows/lint.yaml`: `ghcr.io/qgis/pyqgis4-checker:main-ubuntu` で Qt6 互換チェックを行う `qt6-check` ジョブを追加。
- README・AGENTS.md: 対応バージョン（QGIS 3.40 以上 4.x まで）とローカルでのチェック手順を記載。

Closes #22

## テスト

- pyqgis4-checker の dry-run: 指摘 0 件。
- `bash scripts/test-docker.sh -q` を `qgis/qgis:3.40`・`3.44`・`4.0-trixie`・`4.2-trixie` で実行し、各 241 件成功。
- `.venv/bin/ruff check .`・`.venv/bin/ruff format --check .` 成功。
- QGIS 4.2.2（macOS）で手動確認: プラグイン有効化、ブラウザパネルのツリー展開と右クリック項目。

## 関連

- 設計書: `docs/superpowers/specs/2026-10-24-qgis4-migration-design.md`
- 先行: #21 の PR（AlgorithmWidget 対応、`qgisMaximumVersion` 追加、4.2 の必須化）

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_011cFb7D28ykjf9Jk4241kEs
EOF
```

Expected: PR の URL が表示される。

- [ ] **Step 4: CI の完了を確認し、利用者にマージを依頼する**

Run:

```bash
gh pr checks --watch
```

Expected: `QGIS 3.40`・`QGIS 3.44`・`QGIS 4.0-trixie`・`QGIS 4.2-trixie`・`Ruff`・`PyQGIS 4 Checker` の 6 チェックが成功。マージは利用者が行う。
