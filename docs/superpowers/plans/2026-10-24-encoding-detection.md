# 文字コード自動判定と共通化（PR 1）実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 最低 QGIS を 3.44 に引き上げ、通知・一時ディレクトリの共通モジュールを切り出し、Shapefile の文字コードをローカルの `.dbf` から自動判定して既存の追加経路（ブラウザ・メッシュ索引・`ksj:load_layer`）へ無言で適用する。

**Architecture:** 新モジュール `ksj/messages.py`（通知）、`ksj/temporary_files.py`（一時ディレクトリの寿命管理）、`ksj/encoding_check.py`（判定と適用）を追加し、`layer_loading` と `mesh_index` から共通処理を移す。判定は `.dbf` の先頭レコードの生バイト列（厳密な UTF-8 → cp932）を一次判定、`.cpg` → 言語ID → フォルダ名を補助判定とし、確定した場合だけ `setProviderEncoding()` を呼ぶ。

**Tech Stack:** Python 3.9 互換、PyQGIS（`qgis.core` / `qgis.PyQt`）、GDAL/OGR、pytest + pytest-qgis、Ruff、Docker（`qgis/qgis:3.44` / `4.0-trixie` / `4.2-trixie`）

**Spec:** `docs/superpowers/specs/2026-10-24-kumoy-destination-design.md`（「実装の分割」の 1 番目）

## Global Constraints

- 対応バージョンは QGIS 3.44 以上 4.x まで（Qt 5 / Qt 6 両対応）。Qt は `qgis.PyQt` 経由、enum は `QDialog.DialogCode.Accepted` のように修飾付きで書く（pyqgis4-checker が検査する）。
- Python 3.9 互換。`list[str]` や `X | Y` の型表記、`match` 文は使わない。
- 外部依存を追加しない。パッケージ内は `from . import x` の相対インポート。
- 文言・docstring・コメント・コミットメッセージは日本語。コミットは Conventional Commits（`feat:` `fix:` `docs:` `chore:` `refactor:` `test:`）。
- 通知文言は設計書のとおり。ログは `QgsMessageLog` のタグ `KSJ`。
- 各タスクの最後に `uv run --no-sync ruff check .` と `uv run --no-sync ruff format .` を通す（`uv run` が `uv.lock` を書き換えたら `git checkout uv.lock`）。
- クイック確認は手元の仮想環境（`source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest <対象> -q`）。公式確認は Docker（`bash scripts/test-docker.sh`、`QGIS_TEST_IMAGE=qgis/qgis:4.0-trixie bash scripts/test-docker.sh`、`QGIS_TEST_IMAGE=qgis/qgis:4.2-trixie bash scripts/test-docker.sh`）。手元の `.venv` は QGIS 3.42 だが、この計画のコードは 3.44 固有の API を使わないため回帰確認に使える。
- コミットメッセージ末尾に次の 2 行を付ける。

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
```

---

## ファイル構成

| ファイル | 役割 |
| --- | --- |
| `ksj/messages.py`（新規） | `log_message` / `notify` / `main_window`。GUI の有無を問わず呼べる通知 |
| `ksj/temporary_files.py`（新規） | `workspace()` / `cleanup()` / `release_when_closed()`。一時ディレクトリの寿命管理 |
| `ksj/encoding_check.py`（新規） | `Detection` / `detect_shapefile_encoding()` / `apply_detected_encoding()` / `is_shapefile_layer()` / `source_path()` |
| `ksj/layer_loading.py` | `_cleanup` `_release_when_closed` を削除し共通モジュールを使う。`_finish` で自動判定を適用 |
| `ksj/mesh_index.py` | `log_message` `notify` の定義を `messages` へ移す。`_finish_loading` で自動判定を適用 |
| `ksj/local_storage.py` | `main_window` を `messages` から再エクスポート |
| `ksj/processing_algorithms.py` | `ksj:load_layer` に `ENCODING` を追加 |
| `tests/helpers.py` | `make_shapefile()` / `shapefile_entries()` / `workspaces()` |
| `tests/conftest.py` | `temp_root` fixture（`test_lazy_loading` から移動） |
| `tests/test_messages.py` `tests/test_temporary_files.py` `tests/test_encoding_check.py`（新規） | 各モジュールの単体テスト |
| `metadata.txt` `.github/workflows/test.yaml` `README.md` `AGENTS.md` `tests/test_metadata.py` | 最低バージョンと説明 |

---

### Task 1: 最低対応バージョンを QGIS 3.44 に引き上げる

**Files:**
- Modify: `metadata.txt:3`
- Modify: `tests/test_metadata.py:1-19`
- Modify: `.github/workflows/test.yaml:24`
- Modify: `README.md:7`, `README.md:173-177`, `README.md:181`
- Modify: `AGENTS.md`（「ビルド・テスト・開発コマンド」の段落）

**Interfaces:**
- Produces: なし（宣言と文書のみ）

- [ ] **Step 1: テストを先に変更する**

`tests/test_metadata.py` の 1 行目の docstring と `test_version_range_covers_qgis_3_and_4` を次にする。

```python
"""metadata.txt が QGIS 3.44 から 4.x までの読み込み条件を満たすこと。"""
```

```python
def test_version_range_covers_qgis_3_and_4():
    general = load_metadata()
    # kumoy プラグインと同じ最低バージョン。
    assert general["qgisMinimumVersion"] == "3.44"
    # qgisMaximumVersion が無いと QGIS 4 は上限を 3.99 とみなして読み込まない。
    assert general["qgisMaximumVersion"] == "4.99"
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py -q`
Expected: FAIL（`assert '3.40' == '3.44'`）

- [ ] **Step 3: metadata.txt と CI を変更する**

`metadata.txt` の `qgisMinimumVersion=3.40` を `qgisMinimumVersion=3.44` にする。

`.github/workflows/test.yaml` の matrix を次にする。

```yaml
        qgis: ["3.44", "4.0-trixie", "4.2-trixie"]
```

- [ ] **Step 4: README と AGENTS.md を変更する**

`README.md` 7 行目を次にする。

```
QGIS 3.44 以上 4.x まで（Qt 5・Qt 6 の両方）に対応します。
```

`README.md` の「Docker でテスト」のコマンド例から `QGIS_TEST_IMAGE=qgis/qgis:3.40 bash scripts/test-docker.sh` の行を削除し、続く段落の「QGIS 3.40（最低対応版）・3.44・4.0・4.2 のテストとカバレッジ」を「QGIS 3.44（最低対応版）・4.0・4.2 のテストとカバレッジ」にする。

`AGENTS.md` の「GitHub Actions は同じスクリプトで QGIS 3.40・3.44・4.0・4.2 を確認します」を「QGIS 3.44・4.0・4.2 を確認します」に、「対応バージョンは QGIS 3.40 以上 4.x までで」を「対応バージョンは QGIS 3.44 以上 4.x までで」にする。

- [ ] **Step 5: テストが通ることを確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_metadata.py -q`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add metadata.txt tests/test_metadata.py .github/workflows/test.yaml README.md AGENTS.md
git commit -q -F - <<'EOF'
chore: 最低対応バージョンを QGIS 3.44 に引き上げ

kumoy プラグインと同じ最低バージョンに揃える。CI のマトリクスから 3.40 を外す。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 2: 通知を `ksj/messages.py` へ切り出す

**Files:**
- Create: `ksj/messages.py`
- Create: `tests/test_messages.py`
- Modify: `ksj/mesh_index.py:7-13, 112-123`（`log_message` `notify` の定義を削除し import に置き換える）
- Modify: `ksj/layer_loading.py:22`（import 元を変更）
- Modify: `ksj/local_storage.py:16, 146-148`（`main_window` を再エクスポート）

**Interfaces:**
- Produces: `messages.log_message(message: str, warning: bool = False) -> Qgis.MessageLevel`、`messages.notify(message: str, warning: bool = False) -> None`、`messages.main_window() -> QWidget | None`、`messages.LOG_TAG = "KSJ"`
- 既存の呼び出し `mesh_index.notify` / `layer_loading.notify` / `local_storage.main_window` は同じ名前で使え、テストの `monkeypatch.setattr(layer_loading, "notify", ...)` もそのまま効く。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_messages.py` を作成する。

```python
"""メッセージログとメッセージバーへの通知。"""

from types import SimpleNamespace

from qgis import utils
from qgis.core import Qgis

from ksj import messages


def test_log_message_records_with_ksj_tag_and_returns_level(qgis_app):
    received = []

    def record(message, tag, level, *_):
        received.append((message, tag, level))

    log = qgis_app.messageLog()
    # QGIS 4 は形式付きシグナルを送出し、旧シグナルには本文を送らない。
    signal = getattr(log, "messageReceivedWithFormat", log.messageReceived)
    signal.connect(record)
    try:
        assert messages.log_message("情報") == Qgis.MessageLevel.Info
        assert messages.log_message("注意", warning=True) == Qgis.MessageLevel.Warning
    finally:
        signal.disconnect(record)
    assert received == [
        ("情報", "KSJ", Qgis.MessageLevel.Info),
        ("注意", "KSJ", Qgis.MessageLevel.Warning),
    ]


def test_notify_uses_message_bar_only_when_gui_exists(monkeypatch):
    pushed = []
    bar = SimpleNamespace(
        pushMessage=lambda tag, message, level, duration: pushed.append(
            (tag, message, level, duration)
        )
    )
    monkeypatch.setattr(
        utils,
        "iface",
        SimpleNamespace(messageBar=lambda: bar, mainWindow=lambda: "window"),
    )
    messages.notify("追加しました")
    assert pushed == [("KSJ", "追加しました", Qgis.MessageLevel.Info, 8)]
    assert messages.main_window() == "window"

    monkeypatch.setattr(utils, "iface", None)
    messages.notify("GUIなしでも例外にならない", warning=True)
    assert len(pushed) == 1
    assert messages.main_window() is None
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_messages.py -q`
Expected: FAIL（`ImportError: cannot import name 'messages'`）

- [ ] **Step 3: `ksj/messages.py` を作成する**

```python
"""メッセージログとメッセージバーへの通知。GUI の有無を問わず呼べる。"""

from qgis import utils
from qgis.core import Qgis, QgsMessageLog

LOG_TAG = "KSJ"


def log_message(message, warning=False):
    """KSJタグでメッセージログに残し、使った水準を返す。ワーカースレッドからも呼べる。"""
    level = Qgis.MessageLevel.Warning if warning else Qgis.MessageLevel.Info
    QgsMessageLog.logMessage(message, LOG_TAG, level)
    return level


def notify(message, warning=False):
    """ログに残したうえで、GUIがあればメッセージバーにも表示する。"""
    level = log_message(message, warning)
    if utils.iface is not None:
        utils.iface.messageBar().pushMessage(LOG_TAG, message, level=level, duration=8)


def main_window():
    """ダイアログの親。ヘッドレス環境やテストでは None。"""
    return utils.iface.mainWindow() if utils.iface is not None else None
```

- [ ] **Step 4: 既存モジュールを新モジュールに向ける**

`ksj/mesh_index.py`:
- 112〜123 行目の `def log_message(...)` と `def notify(...)` を削除する。
- `from . import catalog, local_storage, zip_scanner` の直後に `from .messages import notify` を追加する。
- `from qgis.core import (...)` から `QgsMessageLog` を外す（`Qgis` は `MapLayerActionTarget` で使うため残す）。

`ksj/layer_loading.py` 22 行目を `from .messages import log_message, notify` にする。

`ksj/local_storage.py`:
- 146〜148 行目の `def main_window()` を削除する。
- `from .zip_scanner import STORAGE_METADATA` の直前に `from .messages import main_window` を追加する（`configure_loading` と `choose_download_directory` が使うため再エクスポートの noqa は不要）。
- `from qgis import utils` を削除する（`main_window` 以外で使っていない）。

- [ ] **Step 5: テストと lint を通す**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_messages.py tests/test_mesh_index.py tests/test_lazy_loading.py tests/test_local_storage.py -q`
Expected: PASS（既存テストは `mesh_index.notify` `layer_loading.notify` の名前を引き続き差し替えられる）

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format .`
Expected: エラーなし。`git status` で `uv.lock` が変わっていたら `git checkout uv.lock`。

- [ ] **Step 6: コミット**

```bash
git add ksj/messages.py tests/test_messages.py ksj/mesh_index.py ksj/layer_loading.py ksj/local_storage.py
git commit -q -F - <<'EOF'
refactor: 通知とメッセージログを messages モジュールへ切り出す

mesh_index と local_storage に散っていた notify / log_message / main_window を
1 か所にまとめ、後続の kumoy アップロード処理と一時ディレクトリ管理から
循環 import なしで使えるようにする。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 3: 一時ディレクトリの寿命管理を `ksj/temporary_files.py` へ切り出す

**Files:**
- Create: `ksj/temporary_files.py`
- Create: `tests/test_temporary_files.py`
- Modify: `ksj/layer_loading.py:3-4, 20-22, 70-76, 105-132, 157-167`
- Modify: `tests/conftest.py`（`temp_root` を追加）
- Modify: `tests/helpers.py`（`workspaces` を追加）
- Modify: `tests/test_lazy_loading.py:38-49, 61-69, 740-748`

**Interfaces:**
- Produces: `temporary_files.workspace() -> tempfile.TemporaryDirectory`（prefix `ksj-layer-`）、`temporary_files.cleanup(workspace) -> None`、`temporary_files.release_when_closed(workspace, layers: list[QgsMapLayer]) -> None`、`temporary_files.PREFIX = "ksj-layer-"`
- Produces（テスト用）: `conftest.temp_root` fixture（`tempfile.tempdir` を `tmp_path / "temp"` に固定して返す）、`helpers.workspaces(temp_root) -> list[Path]`

- [ ] **Step 1: テスト用の fixture と helper を移す**

`tests/conftest.py` に `import tempfile` を追加し、`storage_settings` の直前に次を追加する。

```python
@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    """ksj-layer-* の作成先を固定し、レイヤー破棄後に残骸がないことを確かめる。"""
    root = tmp_path / "temp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root
```

`tests/helpers.py` の `zip_bytes` の直後に次を追加する。

```python
def workspaces(temp_root):
    """temp_root 配下に残っている一時ディレクトリ。"""
    return sorted(temp_root.glob("ksj-layer-*"))
```

`tests/test_lazy_loading.py` から 38〜49 行目の `temp_root` fixture と `workspaces` 関数を削除し、`from tests.helpers import (...)` に `workspaces` を加える。

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_temporary_files.py` を作成する。

```python
"""一時レイヤー用ディレクトリの作成と、レイヤーが閉じられた後の削除。"""

from pathlib import Path
from types import SimpleNamespace

from qgis.core import QgsProject, QgsVectorLayer

from ksj import temporary_files


def test_workspace_has_plugin_prefix_and_cleanup_removes_it(temp_root):
    workspace = temporary_files.workspace()
    path = Path(workspace.name)
    assert path.is_dir() and path.parent == temp_root
    assert path.name.startswith(temporary_files.PREFIX)
    temporary_files.cleanup(workspace)
    assert not path.exists()


def test_cleanup_failure_is_logged_not_raised(monkeypatch):
    logged = []
    monkeypatch.setattr(
        temporary_files,
        "log_message",
        lambda message, warning=False: logged.append((message, warning)),
    )

    def fail():
        raise OSError("使用中のため削除できません")

    temporary_files.cleanup(SimpleNamespace(name="/tmp/ksj-layer-test", cleanup=fail))
    ((message, warning),) = logged
    assert "使用中のため削除できません" in message and "ksj-layer-test" in message
    assert warning


def test_release_when_closed_waits_for_the_last_layer(
    qgis_app, qgis_new_project, temp_root
):
    project = QgsProject.instance()
    workspace = temporary_files.workspace()
    path = Path(workspace.name)
    layers = [
        QgsVectorLayer("Point?crs=EPSG:4326", name, "memory") for name in ("a", "b")
    ]
    project.addMapLayers(layers, False)
    temporary_files.release_when_closed(workspace, layers)
    project.removeMapLayer(layers[0].id())
    assert path.is_dir()
    project.removeMapLayer(layers[1].id())
    assert not path.exists()
```

`tests/test_lazy_loading.py` の `logged` fixture（61〜69 行目）を次にする。

```python
@pytest.fixture
def logged(monkeypatch):
    """一時ディレクトリ削除の警告ログを (本文, warning) の組で集める。"""
    messages = []
    monkeypatch.setattr(
        temporary_files,
        "log_message",
        lambda message, warning=False: messages.append((message, warning)),
    )
    return messages
```

`from ksj import catalog_browser, layer_loading, local_storage, remote_zip` に `temporary_files` を加える。740〜748 行目の `test_workspace_cleanup_failure_is_logged_not_raised` は `tests/test_temporary_files.py` に移したので削除する。

- [ ] **Step 3: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_temporary_files.py -q`
Expected: FAIL（`ImportError: cannot import name 'temporary_files'`）

- [ ] **Step 4: `ksj/temporary_files.py` を作成する**

```python
"""一時レイヤー用の作業ディレクトリ。生成したレイヤーがすべて閉じられた時点で削除する。"""

import tempfile

from .messages import log_message

PREFIX = "ksj-layer-"


def workspace():
    """取得・展開先の一時ディレクトリ。削除は cleanup() か release_when_closed() で行う。"""
    return tempfile.TemporaryDirectory(prefix=PREFIX)


def cleanup(workspace):
    """一時ディレクトリを削除する。失敗は警告ログに残すだけで、OSの一時領域掃除に任せる。"""
    try:
        workspace.cleanup()
    except OSError as exc:
        log_message(
            f"一時ファイルを削除できません: {workspace.name} ({exc})", warning=True
        )


def release_when_closed(workspace, layers):
    """一時ディレクトリを、そこから生成したレイヤーがすべて閉じられるまで保つ。"""
    remaining = len(layers)

    def release():
        nonlocal remaining
        remaining -= 1
        if remaining == 0:
            cleanup(workspace)

    for layer in layers:
        layer.destroyed.connect(release)
```

- [ ] **Step 5: `ksj/layer_loading.py` を共通モジュールに向ける**

- `import tempfile` を削除し、`from . import local_storage, remote_zip, zip_scanner` を `from . import local_storage, remote_zip, temporary_files, zip_scanner` にする。`from .messages import log_message, notify` は `from .messages import notify` にする。
- `prepare` の冒頭を次にする。

```python
    temporary = temporary_files.workspace() if mode == "temporary" else None
```

- `prepare` の `except Exception:` 節の `_cleanup(temporary)` を `temporary_files.cleanup(temporary)` にする。
- 111〜132 行目の `_cleanup` と `_release_when_closed` を削除する。
- `_finish` の `_release_when_closed(workspace, added)` を `temporary_files.release_when_closed(workspace, added)` に、`finally` の `_cleanup(workspace)` を `temporary_files.cleanup(workspace)` にする。

- [ ] **Step 6: テストと lint を通す**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_temporary_files.py tests/test_lazy_loading.py tests/test_loading_indicator.py -q`
Expected: PASS

Run: `grep -rn "_cleanup\|_release_when_closed" ksj tests`
Expected: 出力なし（旧名の参照が残っていない）

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format .`
Expected: エラーなし

- [ ] **Step 7: コミット**

```bash
git add ksj/temporary_files.py tests/test_temporary_files.py ksj/layer_loading.py tests/conftest.py tests/helpers.py tests/test_lazy_loading.py
git commit -q -F - <<'EOF'
refactor: 一時ディレクトリの寿命管理を temporary_files モジュールへ切り出す

layer_loading の _cleanup / _release_when_closed を共通化し、メッシュ索引経路と
kumoy アップロード処理から循環 import なしで使えるようにする。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 4: Shapefile の文字コード判定（`encoding_check.detect_shapefile_encoding`）

**Files:**
- Create: `ksj/encoding_check.py`
- Create: `tests/test_encoding_check.py`
- Modify: `tests/helpers.py`（`make_shapefile` `shapefile_entries` を追加）

**Interfaces:**
- Produces: `encoding_check.Detection(encoding: str | None, reason: str, confident: bool)`（namedtuple）、`encoding_check.detect_shapefile_encoding(shp_path) -> Detection`、定数 `UTF8 = "UTF-8"`、`SHIFT_JIS = "Shift_JIS"`、`REASON_BYTES = "属性値から判定"`、`REASON_CPG = ".cpg から判定"`、`REASON_LDID = ".dbf の言語IDから判定"`、`REASON_FOLDER = "フォルダ名から判定"`、`UNDETERMINED = "文字コードを判定できませんでした"`
- Produces（テスト用）: `helpers.make_shapefile(path, texts, encoding, cpg=None, ldid=0) -> Path`（`texts` の各要素は str か bytes。bytes はそのまま `.dbf` に書く）、`helpers.shapefile_entries(path) -> list[tuple[str, bytes]]`（`.shp` と同名の全ファイルを ZIP 用の (名前, 内容) にする）

- [ ] **Step 1: テスト用の Shapefile 生成 helper を書く**

`tests/helpers.py` の末尾に追加する。OGR の Python 束縛は文字列を UTF-8 で書くため、プレースホルダーを書いてから `.dbf` のバイト列を直接差し替える。

```python
def make_shapefile(path, texts, encoding, cpg=None, ldid=0, field="name"):
    """texts を属性に持つ点の Shapefile を書く。.dbf の文字列は指定の文字コードで保存する。

    texts の要素が bytes ならそのまま書く（どの文字コードでも復号できない列の試験用）。
    cpg は .cpg の内容（None なら作らない）、ldid は .dbf ヘッダ 30 バイト目の言語ID。
    """
    path = Path(path)
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(4326)
    placeholders = []
    gdal.SetConfigOption("SHAPE_ENCODING", "")
    try:
        dataset = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(str(path))
        layer = dataset.CreateLayer(
            path.stem, srs=crs, geom_type=ogr.wkbPoint, options=["ENCODING="]
        )
        layer.CreateField(ogr.FieldDefn(field, ogr.OFTString))
        for index, text in enumerate(texts):
            raw = text if isinstance(text, bytes) else text.encode(encoding)
            placeholder = f"P{index:02d}".ljust(40, "P").encode("ascii")
            assert len(raw) <= len(placeholder)
            placeholders.append((placeholder, raw.ljust(len(placeholder), b" ")))
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetField(field, placeholder.decode("ascii"))
            feature.SetGeometry(ogr.CreateGeometryFromWkt("POINT (139.7 35.6)"))
            assert layer.CreateFeature(feature) == 0
            feature = None
        layer = dataset = None
    finally:
        gdal.SetConfigOption("SHAPE_ENCODING", None)
    dbf = path.with_suffix(".dbf")
    contents = bytearray(dbf.read_bytes())
    for placeholder, raw in placeholders:
        contents = contents.replace(placeholder, raw)
    contents[29] = ldid
    dbf.write_bytes(bytes(contents))
    cpg_path = path.with_suffix(".cpg")
    if cpg is None:
        if cpg_path.exists():
            cpg_path.unlink()
    else:
        cpg_path.write_text(cpg, encoding="ascii")
    return path


def shapefile_entries(path):
    """Shapefile 一式を ZIP 用の (名前, 内容) にする。"""
    path = Path(path)
    return [
        (sidecar.name, sidecar.read_bytes())
        for sidecar in sorted(path.parent.glob(path.stem + ".*"))
    ]
```

`tests/helpers.py` の冒頭に `from pathlib import Path` を追加する。

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_encoding_check.py` を作成する。テスト関数名は 30 文字以上にし、先頭 30 文字に `utf8` `sjis` `cp932` を含めない。pytest の `tmp_path` は関数名の先頭 30 文字をフォルダ名に使うため、フォルダ名判定を誤って発火させないためである。

```python
"""Shapefile の文字コードを取得済みの .dbf から判定する。"""

import pytest

from ksj import encoding_check
from tests.helpers import make_shapefile

TEXTS = ["札幌市中央区", "函館市"]


@pytest.mark.parametrize(
    "encoding,expected", [("cp932", "Shift_JIS"), ("utf-8", "UTF-8")]
)
def test_attribute_bytes_decide_the_encoding(tmp_path, encoding, expected):
    path = make_shapefile(tmp_path / "city.shp", TEXTS, encoding)
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == (expected, encoding_check.REASON_BYTES, True)


def test_attribute_bytes_override_a_wrong_cpg(tmp_path):
    path = make_shapefile(tmp_path / "city.shp", TEXTS, "cp932", cpg="UTF-8")
    assert encoding_check.detect_shapefile_encoding(path).encoding == "Shift_JIS"


@pytest.mark.parametrize(
    "cpg,expected",
    [("UTF-8", "UTF-8"), ("CP932", "Shift_JIS"), ("SHIFT_JIS", "Shift_JIS")],
)
def test_ascii_only_attributes_fall_back_to_cpg(tmp_path, cpg, expected):
    path = make_shapefile(tmp_path / "city.shp", ["Sapporo"], "ascii", cpg=cpg)
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == (expected, encoding_check.REASON_CPG, False)


def test_ascii_only_attributes_fall_back_to_language_id(tmp_path):
    path = make_shapefile(tmp_path / "city.shp", ["Sapporo"], "ascii", ldid=0x13)
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == ("Shift_JIS", encoding_check.REASON_LDID, False)


@pytest.mark.parametrize(
    "folder,expected", [("UTF-8", "UTF-8"), ("Shift_JIS", "Shift_JIS")]
)
def test_ascii_only_attributes_fall_back_to_folder_name(tmp_path, folder, expected):
    directory = tmp_path / "N03-20240101" / folder
    directory.mkdir(parents=True)
    path = make_shapefile(directory / "city.shp", ["Sapporo"], "ascii")
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == (expected, encoding_check.REASON_FOLDER, False)


def test_undetermined_without_non_ascii_bytes_or_hints(tmp_path):
    path = make_shapefile(tmp_path / "city.shp", ["Sapporo"], "ascii")
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == (None, encoding_check.UNDETERMINED, False)


def test_undecodable_bytes_fall_back_to_hints_without_confidence(tmp_path):
    # 0x81 の後ろの空白は UTF-8 でも cp932 でも不正。
    path = make_shapefile(tmp_path / "city.shp", [b"\x81 "], "ascii", cpg="CP932")
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == ("Shift_JIS", encoding_check.REASON_CPG, False)


def test_missing_dbf_is_reported_as_undetermined(tmp_path):
    detection = encoding_check.detect_shapefile_encoding(tmp_path / "missing.shp")
    assert detection == (None, encoding_check.UNDETERMINED, False)
```

- [ ] **Step 3: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_encoding_check.py -q`
Expected: FAIL（`ImportError: cannot import name 'encoding_check'`）

- [ ] **Step 4: `ksj/encoding_check.py` を作成する**

```python
"""Shapefile の文字コードを取得済みファイルから判定し、レイヤーへ適用する。

国土数値情報の Shapefile は古い配布が cp932、近年は UTF-8 で、両版を
``UTF-8`` / ``Shift_JIS`` フォルダに同梱する配布もある。`.cpg` が無いと QGIS は
UTF-8 で読むため cp932 の属性が文字化けする。ローカルの `.dbf` だけを読み、通信しない。
"""

import struct
from collections import namedtuple
from pathlib import Path

from .messages import log_message

UTF8 = "UTF-8"
SHIFT_JIS = "Shift_JIS"
# 判定に使う先頭レコード数。大きな .dbf でも読み込みを軽く保つ。
SAMPLE_RECORDS = 20
# .dbf ヘッダ 30 バイト目の言語ドライバID。日本語 (cp932) を示す値。
SHIFT_JIS_LDIDS = {0x13, 0x7B}
CPG_NAMES = {
    "UTF-8": UTF8,
    "UTF8": UTF8,
    "CP932": SHIFT_JIS,
    "SHIFT_JIS": SHIFT_JIS,
    "SHIFT-JIS": SHIFT_JIS,
    "SJIS": SHIFT_JIS,
    "932": SHIFT_JIS,
}
# フォルダ名に含まれていれば手がかりにする語（小文字）。
PATH_HINTS = (
    ("utf-8", UTF8),
    ("utf8", UTF8),
    ("shift_jis", SHIFT_JIS),
    ("shift-jis", SHIFT_JIS),
    ("sjis", SHIFT_JIS),
    ("cp932", SHIFT_JIS),
)
REASON_BYTES = "属性値から判定"
REASON_CPG = ".cpg から判定"
REASON_LDID = ".dbf の言語IDから判定"
REASON_FOLDER = "フォルダ名から判定"
UNDETERMINED = "文字コードを判定できませんでした"

# encoding は UTF8 / SHIFT_JIS / None。reason は利用者向けの根拠。
# confident は属性値のバイト列で判定したか（補助判定なら False）。
Detection = namedtuple("Detection", "encoding reason confident")


def sidecar(shp_path, suffix):
    """同名の付属ファイル。大文字拡張子の配布にも対応する。"""
    path = Path(shp_path)
    for candidate in (path.with_suffix(suffix), path.with_suffix(suffix.upper())):
        if candidate.is_file():
            return candidate
    return path.with_suffix(suffix)


def dbf_text_samples(dbf_path):
    """先頭レコードの文字列フィールド（型 C）の生バイト列。"""
    with open(dbf_path, "rb") as source:
        header = source.read(32)
        if len(header) < 32:
            return []
        record_count, header_length, record_length = struct.unpack(
            "<IHH", header[4:12]
        )
        fields = []
        while source.tell() + 32 <= header_length:
            descriptor = source.read(32)
            if len(descriptor) < 32 or descriptor[0] == 0x0D:
                break
            fields.append((chr(descriptor[11]), descriptor[16]))
        source.seek(header_length)
        samples = []
        for _ in range(min(record_count, SAMPLE_RECORDS)):
            record = source.read(record_length)
            if len(record) < record_length:
                break
            position = 1  # 先頭バイトは削除フラグ
            for field_type, length in fields:
                if field_type == "C":
                    samples.append(record[position : position + length].strip(b"\x00 "))
                position += length
    return samples


def has_non_ascii(samples):
    return any(byte > 0x7F for sample in samples for byte in sample)


def decodes(samples, codec):
    try:
        for sample in samples:
            sample.decode(codec)
    except UnicodeDecodeError:
        return False
    return True


def hint(shp_path):
    """属性値で決まらないときの補助判定。.cpg → 言語ID → フォルダ名の順。"""
    cpg = sidecar(shp_path, ".cpg")
    if cpg.is_file():
        try:
            name = cpg.read_text(encoding="ascii", errors="ignore").strip().upper()
        except OSError:
            name = ""
        if name in CPG_NAMES:
            return CPG_NAMES[name], REASON_CPG
    try:
        with open(sidecar(shp_path, ".dbf"), "rb") as source:
            header = source.read(32)
    except OSError:
        header = b""
    if len(header) >= 32 and header[29] in SHIFT_JIS_LDIDS:
        return SHIFT_JIS, REASON_LDID
    # 国土数値情報は UTF-8 版と Shift_JIS 版を同名のフォルダで同梱することがある。
    for folder in reversed(Path(shp_path).parent.parts):
        lowered = folder.lower()
        for token, encoding in PATH_HINTS:
            if token in lowered:
                return encoding, REASON_FOLDER
    return None, UNDETERMINED


def detect_shapefile_encoding(shp_path):
    """取得済み Shapefile の文字コードを判定する。通信しない。"""
    try:
        samples = dbf_text_samples(sidecar(shp_path, ".dbf"))
    except OSError:
        samples = []
    if has_non_ascii(samples):
        # UTF-8 の復号は厳密で、cp932 の日本語が偶然通ることはまずない。
        if decodes(samples, "utf-8"):
            return Detection(UTF8, REASON_BYTES, True)
        if decodes(samples, "cp932"):
            return Detection(SHIFT_JIS, REASON_BYTES, True)
    encoding, reason = hint(shp_path)
    return Detection(encoding, reason, False)
```

- [ ] **Step 5: テストと lint を通す**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_encoding_check.py -q`
Expected: PASS

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format .`
Expected: エラーなし

- [ ] **Step 6: コミット**

```bash
git add ksj/encoding_check.py tests/test_encoding_check.py tests/helpers.py
git commit -q -F - <<'EOF'
feat: Shapefile の文字コードを .dbf の属性値と付属情報から判定する

先頭レコードの文字列フィールドを厳密な UTF-8 → cp932 の順に復号して一次判定し、
決まらないときは .cpg、言語ID、フォルダ名を補助判定に使う。通信しない。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 5: 判定結果をレイヤーへ適用し、ブラウザ経路とメッシュ索引経路に組み込む

**Files:**
- Modify: `ksj/encoding_check.py`（`source_path` `is_shapefile_layer` `apply_detected_encoding` を追加）
- Modify: `ksj/layer_loading.py:20, 150-156`
- Modify: `ksj/mesh_index.py`（import と `_finish_loading` のレイヤー生成部）
- Test: `tests/test_encoding_check.py`、`tests/test_lazy_loading.py`、`tests/test_mesh_index.py`

**Interfaces:**
- Produces: `encoding_check.source_path(layer) -> Path`（`"パス|layername=名前"` からパスだけ）、`encoding_check.is_shapefile_layer(layer) -> bool`、`encoding_check.apply_detected_encoding(layer) -> Detection | None`（Shapefile 以外は None。判定できた場合は `setProviderEncoding()` 済み）
- Consumes: Task 4 の `detect_shapefile_encoding`、Task 2 の `log_message`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_encoding_check.py` の冒頭 import に `from qgis.core import QgsVectorLayer` と `from tests.helpers import make_shapefile, point_file` を加え、末尾に追加する。

```python
def test_apply_fixes_cp932_shapefile_without_cpg_and_logs(tmp_path, monkeypatch):
    logs = []
    monkeypatch.setattr(
        encoding_check, "log_message", lambda message, warning=False: logs.append(message)
    )
    path = make_shapefile(tmp_path / "city.shp", TEXTS, "cp932")
    layer = QgsVectorLayer(str(path), "city", "ogr")
    assert layer.isValid()
    detection = encoding_check.apply_detected_encoding(layer)
    assert detection.encoding == "Shift_JIS"
    assert layer.dataProvider().encoding() == "Shift_JIS"
    assert [feature["name"] for feature in layer.getFeatures()] == TEXTS
    assert logs == ["文字コードを Shift_JIS と判定して適用: city.shp"]


def test_apply_reads_unicode_shapefile_and_ignores_other_formats(tmp_path):
    path = make_shapefile(tmp_path / "city.shp", TEXTS, "utf-8")
    layer = QgsVectorLayer(str(path), "city", "ogr")
    assert encoding_check.apply_detected_encoding(layer).encoding == "UTF-8"
    assert [feature["name"] for feature in layer.getFeatures()] == TEXTS
    geojson = QgsVectorLayer(str(point_file(tmp_path)), "dams", "ogr")
    assert encoding_check.apply_detected_encoding(geojson) is None


def test_apply_leaves_undetermined_layer_untouched(tmp_path, monkeypatch):
    logs = []
    monkeypatch.setattr(
        encoding_check, "log_message", lambda message, warning=False: logs.append(message)
    )
    path = make_shapefile(tmp_path / "city.shp", ["Sapporo"], "ascii")
    layer = QgsVectorLayer(str(path), "city", "ogr")
    before = layer.dataProvider().encoding()
    assert encoding_check.apply_detected_encoding(layer).encoding is None
    assert layer.dataProvider().encoding() == before
    assert logs == []


def test_source_path_strips_sublayer_suffix(tmp_path):
    path = make_shapefile(tmp_path / "city.shp", TEXTS, "utf-8")
    layer = QgsVectorLayer(f"{path}|layername=city", "city", "ogr")
    assert encoding_check.source_path(layer) == path
    assert encoding_check.is_shapefile_layer(layer)
```

`tests/test_lazy_loading.py` の `from tests.helpers import (...)` に `make_shapefile, shapefile_entries` を加え、末尾に追加する。

```python
@pytest.mark.parametrize("mode", ["save", "temporary"])
def test_shapefile_without_cpg_is_added_with_detected_encoding(
    qgis_app, qgis_new_project, storage_settings, http_data, tmp_path, mode
):
    source = make_shapefile(tmp_path / "city.shp", ["札幌市中央区"], "cp932")
    http_data.update(range_support=True, body=zip_bytes(shapefile_entries(source)))
    QgsSettings().setValue(local_storage.MODE_KEY, mode)
    if mode == "save":
        storage_settings.mkdir()
        QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    (item,) = listing(qgis_app, http_data)
    assert item.handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    (layer,) = QgsProject.instance().mapLayers().values()
    assert layer.dataProvider().encoding() == "Shift_JIS"
    assert next(layer.getFeatures())["name"] == "札幌市中央区"
```

`tests/test_mesh_index.py` の `from tests.helpers import make_raster, make_vector, pump_until` に `make_shapefile, shapefile_entries` を加え、末尾に追加する。

```python
def test_mesh_applies_detected_shapefile_encoding(
    qgis_app, qgis_new_project, tmp_path, monkeypatch
):
    (tmp_path / "src").mkdir()
    source = make_shapefile(tmp_path / "src" / "city.shp", ["札幌市中央区"], "cp932")
    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for name, contents in shapefile_entries(source):
            output.writestr(name, contents)
    monkeypatch.setattr(
        local_storage,
        "_download",
        lambda url, path, *args: path.write_bytes(archive.read_bytes()),
    )
    resource = {
        "region": "5339",
        "year": "2024年",
        "filename": "data.zip",
        "url": "https://example.org/data.zip",
    }
    index = mesh_index.add_mesh_index("行政区域", [resource])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    (layer,) = [
        layer
        for layer in QgsProject.instance().mapLayers().values()
        if layer.id() != index.id()
    ]
    assert layer.dataProvider().encoding() == "Shift_JIS"
    assert next(layer.getFeatures())["name"] == "札幌市中央区"
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_encoding_check.py tests/test_lazy_loading.py tests/test_mesh_index.py -k "apply or source_path or detected_encoding" -q`
Expected: FAIL（`AttributeError: module 'ksj.encoding_check' has no attribute 'apply_detected_encoding'`、統合テストは `encoding() == 'UTF-8'` のままで失敗）

- [ ] **Step 3: 適用関数を実装する**

`ksj/encoding_check.py` の末尾に追加する。

```python
def source_path(layer):
    """レイヤーの参照先ファイル。サブレイヤーの "パス|layername=名前" からもパスだけ取り出す。"""
    return Path(layer.source().split("|", 1)[0])


def is_shapefile_layer(layer):
    return layer.providerType() == "ogr" and source_path(layer).suffix.lower() == ".shp"


def apply_detected_encoding(layer):
    """判定した文字コードをレイヤーに設定する。判定不能なら QGIS の既定に任せる。

    Shapefile 以外は None を返す。GeoJSON などは GDAL が UTF-8 固定で、
    QGIS は setProviderEncoding() を無視する。
    """
    if not is_shapefile_layer(layer):
        return None
    path = source_path(layer)
    detection = detect_shapefile_encoding(path)
    if detection.encoding is None:
        return detection
    if layer.dataProvider().encoding() != detection.encoding:
        layer.setProviderEncoding(detection.encoding)
        log_message(f"文字コードを {detection.encoding} と判定して適用: {path.name}")
    return detection
```

- [ ] **Step 4: ブラウザ経路に組み込む**

`ksj/layer_loading.py` の `from . import local_storage, remote_zip, temporary_files, zip_scanner` に `encoding_check` を加え（アルファベット順）、`_finish` のレイヤー生成ループを次にする。

```python
        for provider, source, title in result["layers"]:
            layer_type = QgsRasterLayer if provider == "gdal" else QgsVectorLayer
            layer = layer_type(source, title, provider)
            if not layer.isValid():
                failed.append(title)
                continue
            if provider == "ogr":
                encoding_check.apply_detected_encoding(layer)
            added.append(layer)
```

- [ ] **Step 5: メッシュ索引経路に組み込む**

`ksj/mesh_index.py` の `from . import catalog, local_storage, zip_scanner` に `encoding_check` を加え、`_finish_loading` のレイヤー生成ループを次にする。

```python
    for provider, path, name, uri in selected:
        layer_class = QgsVectorLayer if provider == "ogr" else QgsRasterLayer
        layer = layer_class(uri, name, provider)
        if not layer.isValid():
            failed.append(name)
            continue
        if provider == "ogr":
            encoding_check.apply_detected_encoding(layer)
        layer.setCustomProperty(RESOURCE_PROPERTY, url)
        project.addMapLayer(layer)
        added += 1
```

- [ ] **Step 6: テストと lint を通す**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_encoding_check.py tests/test_lazy_loading.py tests/test_mesh_index.py -q`
Expected: PASS

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format .`
Expected: エラーなし

- [ ] **Step 7: コミット**

```bash
git add ksj/encoding_check.py ksj/layer_loading.py ksj/mesh_index.py tests/test_encoding_check.py tests/test_lazy_loading.py tests/test_mesh_index.py
git commit -q -F - <<'EOF'
feat: 追加した Shapefile に判定した文字コードを自動で適用する

ブラウザからの追加とメッシュ索引からの追加で、.cpg の無い cp932 の Shapefile が
文字化けしないようにする。判定できない場合は QGIS の既定に任せ、適用時はログに残す。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 6: `ksj:load_layer` に文字コードパラメータを追加する

**Files:**
- Modify: `ksj/processing_algorithms.py:6-18, 20, 366-412`
- Test: `tests/test_processing.py`

**Interfaces:**
- Produces: `ksj:load_layer` の `ENCODING`（enum、`ENCODING_OPTIONS = ["自動判定", "UTF-8", "Shift_JIS", "EUC-JP"]`、既定 0）
- Consumes: Task 5 の `encoding_check.apply_detected_encoding`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_processing.py` の `from tests.helpers import (...)` に `make_shapefile` を加え、`test_load_invalid_layer_fails` の直後に追加する。

```python
def test_load_layer_detects_or_forces_shapefile_encoding(processing_provider, tmp_path):
    path = make_shapefile(tmp_path / "city.shp", ["札幌市"], "cp932")
    detected = run("load_layer", {"SOURCE": str(path), "PROVIDER": "ogr"})["OUTPUT"]
    assert detected.dataProvider().encoding() == "Shift_JIS"
    assert next(detected.getFeatures())["name"] == "札幌市"
    forced = run(
        "load_layer", {"SOURCE": str(path), "PROVIDER": "ogr", "ENCODING": 1}
    )["OUTPUT"]
    assert forced.dataProvider().encoding() == "UTF-8"
    assert next(forced.getFeatures())["name"] != "札幌市"
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_processing.py -k encoding -q`
Expected: FAIL（`encoding() == 'UTF-8'` のまま）

- [ ] **Step 3: パラメータと適用を実装する**

`ksj/processing_algorithms.py`:
- `from qgis.core import (...)` に `QgsProcessingParameterEnum` を加える。
- `from . import catalog, local_storage, zip_scanner` を `from . import catalog, encoding_check, local_storage, zip_scanner` にする。
- `MAX_PAGE_SIZE = 100` の直後に追加する。

```python
# ksj:load_layer の ENCODING。先頭は Shapefile の自動判定、以降は明示指定。
ENCODING_OPTIONS = ["自動判定", "UTF-8", "Shift_JIS", "EUC-JP"]
```

- `LoadLayer.shortHelpString` の末尾（`通常ファイルを参照するため、...` の後）に次の文を加える。

```
"ENCODINGはShapefileの文字コード。既定の自動判定は.dbfの属性値と.cpgなどから決め、"
"判定できない場合はQGISの既定に従います。GeoJSON・GMLなどはUTF-8固定で指定は無視されます。"
```

- `LoadLayer.initAlgorithm` の `self.add_string("NAME", ...)` の直後に追加する。

```python
        self.addParameter(
            QgsProcessingParameterEnum(
                "ENCODING",
                "文字コード（Shapefile）",
                options=ENCODING_OPTIONS,
                defaultValue=0,
            )
        )
```

- `LoadLayer.processAlgorithm` の `if not layer.isValid(): raise ...` の直後に追加する。

```python
        if provider == "ogr":
            choice = self.parameterAsEnum(parameters, "ENCODING", context)
            if choice == 0:
                encoding_check.apply_detected_encoding(layer)
            else:
                layer.setProviderEncoding(ENCODING_OPTIONS[choice])
```

- [ ] **Step 4: テストと lint を通す**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_processing.py tests/test_processing_widgets.py -q`
Expected: PASS（選択式画面は `CHOICES` に無いパラメータを標準ウィジェットで表示する）

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format .`
Expected: エラーなし

- [ ] **Step 5: コミット**

```bash
git add ksj/processing_algorithms.py tests/test_processing.py
git commit -q -F - <<'EOF'
feat: ksj:load_layer に文字コードの自動判定と指定を追加

Shapefile を Processing から読む場合も文字化けせずに後続処理へ渡せるようにする。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 7: README・AGENTS.md の更新と全体検証

**Files:**
- Modify: `README.md`（「追加方法・保存先と再利用」「保存したデータを地図へ読み込む」「Python・バッチ処理で利用する」「構成」）
- Modify: `AGENTS.md`（「プロジェクト構成とモジュール」）

- [ ] **Step 1: README を更新する**

「追加方法・保存先と再利用」の 2 つの箇条書きの直後（「ZIP・フォルダの閲覧には…」の段落の前）に段落を追加する。

```
Shapefile の文字コードは、取得したファイルの属性値と `.cpg`・言語ID・フォルダ名から自動判定して適用します。判定の結果はメッセージログ（タグ `KSJ`）で確認できます。判定できない場合は QGIS の既定に従うため、文字化けしたときはレイヤープロパティで文字コードを変更してください。GeoJSON・GML・GeoPackage は UTF-8 固定です。
```

「保存したデータを地図へ読み込む」の手順 4 を次にする。

```
4. 必要ならレイヤー名と**文字コード**（既定は Shapefile の自動判定）を指定し、実行します。選んだレイヤーが地図に追加され、後続のProcessing解析に利用できます。
```

「Python・バッチ処理で利用する」の表の `ksj:load_layer` 行を次にする。

```
| `ksj:load_layer`        | `SOURCE`、`PROVIDER`（`ogr` / `gdal`）、任意の `NAME`、`ENCODING`（0: 自動判定、1: UTF-8、2: Shift_JIS、3: EUC-JP） | 単一レイヤー `OUTPUT`                               |
```

「構成」の表に次の行を加える（`ksj/layer_loading.py` の行の後）。

```
| `ksj/encoding_check.py`        | Shapefile の文字コード判定とレイヤーへの適用                     |
| `ksj/temporary_files.py`       | 一時レイヤー用ディレクトリの作成と削除                           |
| `ksj/messages.py`              | メッセージログ・メッセージバーへの通知                           |
```

- [ ] **Step 2: AGENTS.md を更新する**

「プロジェクト構成とモジュール」の 1 文目の列挙に「文字コード判定 (`encoding_check.py`)、通知 (`messages.py`)、一時ディレクトリ (`temporary_files.py`)」を加える。

- [ ] **Step 3: 全体検証**

Run: `bash scripts/test-docker.sh`
Expected: 全テスト PASS（QGIS 3.44）

Run: `QGIS_TEST_IMAGE=qgis/qgis:4.0-trixie bash scripts/test-docker.sh && QGIS_TEST_IMAGE=qgis/qgis:4.2-trixie bash scripts/test-docker.sh`
Expected: 全テスト PASS

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format --check .`
Expected: エラーなし

Run: README「Qt6 互換チェック」の `docker run ... pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log .`、続けて `grep -v "^$" pyqt6_checker.log | grep -i -E "ksj/(messages|temporary_files|encoding_check|layer_loading|mesh_index|processing_algorithms)" || echo "指摘なし"`
Expected: 「指摘なし」（dry run は常に exit 0 なのでログで判断する）

- [ ] **Step 4: コミット**

```bash
git add README.md AGENTS.md
git commit -q -F - <<'EOF'
docs: 文字コードの自動判定と新モジュールの説明を追加

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

- [ ] **Step 5: PR を作る**

設計書のコミット（`b46c665`）を含む現在のブランチ `feat/kumoy-destination` を `git branch -m feat/encoding-detection` で改名し、本 PR に使う。PR 2・PR 3 はこのブランチから順に派生させる。PR 本文には影響範囲、`bash scripts/test-docker.sh` の結果、設計書へのリンクを書く。
