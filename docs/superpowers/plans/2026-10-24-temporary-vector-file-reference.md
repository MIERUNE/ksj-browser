# 一時ベクタレイヤーを一時ファイル参照にする 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ブラウザの「一時レイヤーとして追加」で、ベクタをメモリレイヤーへ複製せず、ラスタと同じく一時ファイルを参照させる。

**Architecture:** ワーカー（`prepare`）は取得・展開とサブレイヤー列挙だけを行い、`(provider, source, title)` の一覧と `tempfile.TemporaryDirectory` を返す。GUI（`_finish`）は save / temporary の区別なくレイヤーを生成してプロジェクトへ追加し、一時モードでは追加に成功したレイヤー全部の `destroyed` を購読して、参照数がゼロになった時点で一時ディレクトリを削除する。`QgsVectorLayer.materialize()` と `QgsProcessingContext` の受け渡しは削除する。

**Tech Stack:** Python 3.9 以上、QGIS 3.40 以上（PyQGIS / `qgis.PyQt`）、pytest + pytest-qgis、Ruff。追加依存なし。

**Spec:** `docs/superpowers/specs/2026-10-24-temporary-vector-file-reference-design.md`

## Global Constraints

- Python 3.9 以上、QGIS 3.40 以上 4.x まで。Qt は `qgis.PyQt` 経由。追加依存なし。
- enum は修飾付き表記（例: `QgsTask.Flag.CanCancel`）。pyqgis4-checker の dry run に新たな指摘を出さない。
- パッケージ内部は相対インポート（`from . import local_storage`）。
- コード中の文言・docstring・コミットメッセージ・PR 説明は日本語。コミットは Conventional Commits（`feat:` / `fix:` / `docs:` / `test:`）。
- クラスは既存の `LayerLoadTask`（`QgsTask` 継承）のみ。新しいクラスは追加しない。寿命管理はクロージャで行う。
- 一時ディレクトリの削除失敗（`OSError`）は `QgsMessageLog` に警告を残して握りつぶす。レイヤー破棄のスロット内で例外を投げない。
- 設定ダイアログの説明文（確定）: 「一時レイヤーは一時ファイルを参照し、レイヤーを閉じると削除します。残す場合は別途保存してください。」
- テスト実行（ホスト、反復用）: `source setup_qgis_env.sh && .venv/bin/python -m pytest <対象> -v`
- テスト実行（Docker、最終確認用）: `bash scripts/test-docker.sh`
- Lint: `.venv/bin/ruff check .` と `.venv/bin/ruff format --check .`（`uv run` は `uv.lock` を書き換えるため使わない。使った場合は `git checkout uv.lock` で戻す）
- `imgs/loading-settings.png` の差し替えは範囲外。

---

## ファイル構成

新規ファイルはない。

| ファイル | 責務 | 変更内容 |
| --- | --- | --- |
| `ksj/layer_loading.py` | ブラウザからのレイヤー追加タスク。取得（ワーカー）とプロジェクトへの追加（GUI） | `_materialize` と `QgsProcessingContext` の配管を削除し、`_release_when_closed` と `_cleanup` を追加。`_finish` を save / temporary 共通化 |
| `ksj/local_storage.py` | 保存先・追加方法の設定と取得 | 設定ダイアログの説明文のみ |
| `README.md` | 利用者向け説明 | 「一時レイヤーとして追加」の説明文 |
| `tests/test_lazy_loading.py` | ブラウザ経由の追加を実 HTTP・実 QGIS で検証 | `providerType() == "memory"` 前提の修正、materialize テストの削除、一時ファイル寿命のテスト追加 |

---

### Task 1: 一時ベクタレイヤーを一時ファイル参照にし、全レイヤーが閉じるまで一時ディレクトリを保つ

**Files:**
- Modify: `ksj/layer_loading.py:1-205`（import、`prepare`、`_materialize` 削除、`_finish`、`LayerLoadTask`）
- Test: `tests/test_lazy_loading.py`

**Interfaces:**
- Consumes: `remote_zip.saved_member(url, member, directory) -> str | None`、`remote_zip.ensure_member(url, member, directory, is_canceled, progress) -> str`、`local_storage.ensure_local_data(url, directory, is_canceled, progress) -> str`、`local_storage._check_canceled(is_canceled)`、`zip_scanner.provider_key(path) -> str`、`zip_scanner.MULTILAYER_EXTENSIONS`、`mesh_index.notify(message, warning=False)`（いずれも既存、変更しない）
- Produces:
  - `prepare(task, url, member, name, mode, directory) -> dict`：`{"layers": [(provider: str, source: str, title: str), ...], "temporary": tempfile.TemporaryDirectory | None}`。`context` キーは無くなる。
  - `_release_when_closed(workspace: tempfile.TemporaryDirectory, layers: list[QgsMapLayer]) -> None`：`layers` が空なら即 `workspace.cleanup()`。それ以外は各レイヤーの `destroyed` を購読し、最後の 1 つが破棄された時点で `workspace.cleanup()` を呼ぶ。Task 2 で `workspace.cleanup()` の呼び出しを `_cleanup(workspace)` に差し替える。
  - `LayerLoadTask` から `feedback` 属性と `cancel()` オーバーライドが無くなる。

- [x] **Step 1: 既存テストを新しい挙動に合わせて書き換え、寿命管理のテストを追加する**

`tests/test_lazy_loading.py` を次のとおり変更する。

1-a. import を変更する。`tempfile` を追加し、`QThread` を外す（Step 1-f で唯一の利用箇所を削除するため）。

```python
import gc
import tempfile
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from osgeo import ogr, osr
from qgis.core import (
    QgsApplication,
    QgsBrowserModel,
    QgsDataItem,
    QgsProject,
    QgsProviderRegistry,
    QgsSettings,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QApplication, QMenu, QRadioButton
```

1-b. `resource` 関数の直前（`from tests.helpers import (...)` の直後）に fixture を追加する。一時ディレクトリの作成先を固定し、残骸の有無を確認できるようにする。

```python
@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    """ksj-layer-* の作成先を固定し、レイヤー破棄後に残骸がないことを確かめる。"""
    root = tmp_path / "temp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


def workspaces(temp_root):
    return sorted(temp_root.glob("ksj-layer-*"))
```

1-c. `test_setting_change_applies_to_already_visible_item` を次の本文に置き換える（一時レイヤーは `ogr` で保存先の外を参照し、save へ切り替えた 2 枚目だけが保存先を参照する）。

```python
def test_setting_change_applies_to_already_visible_item(
    qgis_app, qgis_new_project, storage_settings, http_data
):
    archive_with_unselected_data(http_data)
    item = listing(qgis_app, http_data)[0]
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    assert item.handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1
    assert layers[0].providerType() == "ogr"
    assert Path(layers[0].source()).is_file()
    assert storage_settings not in Path(layers[0].source()).parents
    assert next(layers[0].getFeatures())["name"] == "試験ダム"
    assert layers[0].crs().authid() == "EPSG:4326"
    assert not storage_settings.exists()
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    QgsSettings().setValue(local_storage.MODE_KEY, "save")
    assert item.handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 2
    assert {layer.providerType() for layer in layers} == {"ogr"}
    assert {
        storage_settings in Path(layer.source()).parents for layer in layers
    } == {True, False}
```

1-d. `test_file_context_menu_adds_selected_layer_using_current_settings` の末尾、`if mode == "save": ... else: ...` のブロックを次に置き換える。

```python
    assert layer.providerType() == "ogr"
    assert Path(layer.source()).is_file()
    if mode == "save":
        assert storage_settings in Path(layer.source()).parents
    else:
        assert storage_settings not in Path(layer.source()).parents
        assert not storage_settings.exists()
```

1-e. `test_drag_fetches_nothing_until_drop_and_uses_temporary_preference` の末尾 3 行を次に置き換える。

```python
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1 and layers[0].providerType() == "ogr"
    assert Path(layers[0].source()).is_file()
    assert not storage_settings.exists()
```

1-f. `test_temporary_materialization_runs_in_worker_and_returns_gui_owned_layer` を関数ごと削除する（`materialize` を使わなくなるため前提が消える）。

1-g. `test_temporary_raster_keeps_file_until_layer_is_removed` の直後に、ベクタ版と複数サブレイヤー版を追加する。

```python
def test_temporary_vector_keeps_file_until_layer_is_removed(
    qgis_app, qgis_new_project, storage_settings, http_data, temp_root
):
    archive_with_unselected_data(http_data)
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    assert listing(qgis_app, http_data)[0].handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layer = list(QgsProject.instance().mapLayers().values())[0]
    path = Path(layer.source())
    assert layer.providerType() == "ogr" and path.is_file()
    assert next(layer.getFeatures())["name"] == "試験ダム"
    assert len(workspaces(temp_root)) == 1
    assert workspaces(temp_root)[0] in path.parents
    QgsProject.instance().removeMapLayer(layer.id())
    qgis_app.processEvents()
    assert not path.exists()
    assert not workspaces(temp_root)
    assert not storage_settings.exists()


def test_temporary_sublayers_share_workspace_until_all_are_removed(
    qgis_app, qgis_new_project, storage_settings, http_data, tmp_path, temp_root
):
    source = make_vector(tmp_path / "multiple.gpkg", ["rivers", "stations"])
    http_data.update(
        range_support=True, body=zip_bytes([("multiple.gpkg", source.read_bytes())])
    )
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    assert listing(qgis_app, http_data)[0].handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert {layer.name() for layer in layers} == {"rivers", "stations"}
    # サブレイヤーの source は "パス|layername=名前" の形。
    path = Path(layers[0].source().split("|")[0])
    assert path.is_file() and len(workspaces(temp_root)) == 1
    QgsProject.instance().removeMapLayer(layers[0].id())
    qgis_app.processEvents()
    # 片方を閉じただけでは、残ったレイヤーのファイルを消さない。
    assert path.is_file() and len(workspaces(temp_root)) == 1
    assert layers[1].isValid() and layers[1].featureCount() == 1
    QgsProject.instance().removeMapLayer(layers[1].id())
    qgis_app.processEvents()
    assert not path.exists()
    assert not workspaces(temp_root)
```

1-h. `test_cancel_task_prevents_late_layer_addition` に `temp_root` を加え、残骸がないことを確認する。

```python
def test_cancel_task_prevents_late_layer_addition(
    qgis_app, qgis_new_project, storage_settings, http_data, temp_root
):
    archive_with_unselected_data(http_data)
    item = listing(qgis_app, http_data)[0]
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    http_data["delay"] = 0.1
    item.handleDoubleClick()
    ended = termination_of(next(iter(layer_loading.pending.values())))
    layer_loading.cancel_pending()
    pump_until(qgis_app, ended, timeout=10)
    qgis_app.processEvents()
    assert not QgsProject.instance().mapLayers()
    assert not storage_settings.exists()
    assert not workspaces(temp_root)
```

1-i. `test_multilayer_file_is_inspected_only_when_added` の最後の assert を次に置き換える。

```python
    assert {layer.providerType() for layer in layers} == {"ogr"}
    assert all(
        (storage_settings in Path(layer.source()).parents) == (mode == "save")
        for layer in layers
    )
```

1-j. `test_temporary_sublayers_share_workspace_until_all_are_removed` の直後に、保存済みデータを再利用したときに保存データを消さないテストを追加する。

```python
def test_temporary_layer_reuses_saved_data_without_deleting_it(
    qgis_app, qgis_new_project, storage_settings, http_data, temp_root
):
    archive_with_unselected_data(http_data)
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    saved = Path(fetch(qgis_app, http_data, storage_settings, "point.geojson"))
    assert saved.is_file()
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    item = listing(qgis_app, http_data)[0]
    before = len(http_data["requests"])
    assert item.handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layer = list(QgsProject.instance().mapLayers().values())[0]
    # 保存済みの選択データを通信せず参照する。
    assert Path(layer.source()) == saved
    assert len(http_data["requests"]) == before
    QgsProject.instance().removeMapLayer(layer.id())
    qgis_app.processEvents()
    # 閉じても保存データは残り、空の一時ディレクトリだけが消える。
    assert saved.is_file()
    assert not workspaces(temp_root)
```

- [x] **Step 2: テストを実行して、新しい期待が失敗することを確かめる**

Run:

```bash
source setup_qgis_env.sh && .venv/bin/python -m pytest tests/test_lazy_loading.py -v -k "setting_change or context_menu or drag_fetches or temporary_vector or sublayers_share or multilayer_file or reuses_saved"
```

Expected: `temporary` を使うケースが `assert 'memory' == 'ogr'`、または `Path(...).is_file()` の失敗で FAIL する。save のパラメータと `test_cancel_task_prevents_late_layer_addition` は PASS してよい。

- [x] **Step 3: `ksj/layer_loading.py` を書き換える**

3-a. import を次にする（`QgsFeatureRequest`、`QgsFeedback`、`QgsProcessingContext` を外す）。

```python
"""ブラウザの追加操作をタスク化し、記憶した保存方式でレイヤーを追加する。"""

import json
import tempfile
from collections import namedtuple
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsMimeDataUtils,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsTask,
    QgsVectorLayer,
)
from qgis.gui import QgsCustomDropHandler
from qgis.PyQt.QtCore import QObject, pyqtSignal

from . import local_storage, remote_zip, zip_scanner
from .local_storage import DownloadError
from .mesh_index import notify
```

3-b. `prepare` を次に置き換える。`QgsProcessingContext` と `_materialize` の呼び出し、`pushToThread` を外す。

```python
def prepare(task, url, member, name, mode, directory):
    """ワーカーで必要なファイルのみ取得。QGISプロジェクトには触れない。"""
    temporary = (
        tempfile.TemporaryDirectory(prefix="ksj-layer-")
        if mode == "temporary"
        else None
    )
    try:
        destination = temporary.name if temporary else directory
        if member:
            # 一時レイヤーでも、保存済みの選択データがあれば通信せず再利用する。
            saved = (
                remote_zip.saved_member(url, member, directory) if temporary else None
            )
            path = saved or remote_zip.ensure_member(
                url, member, destination, task.isCanceled, task.setProgress
            )
        else:
            path = local_storage.ensure_local_data(
                url, destination, task.isCanceled, task.setProgress
            )
        local_storage._check_canceled(task.isCanceled)
        if zip_scanner.provider_key(path) == "gdal":
            layers = [("gdal", path, name)]
        elif Path(path).suffix.lower() in zip_scanner.MULTILAYER_EXTENSIONS:
            provider = QgsProviderRegistry.instance().providerMetadata("ogr")
            layers = [
                ("ogr", sublayer.uri(), sublayer.name())
                for sublayer in provider.querySublayers(path)
            ]
        else:
            layers = [("ogr", path, name)]
        if not layers:
            raise DownloadError("追加可能なレイヤーがありません。")
        return {"layers": layers, "temporary": temporary}
    except Exception:
        if temporary:
            temporary.cleanup()
        raise
```

3-c. `_materialize` 関数を丸ごと削除し、その位置に `_release_when_closed` を置く。

```python
def _release_when_closed(workspace, layers):
    """一時ディレクトリを、そこから生成したレイヤーがすべて閉じられるまで保つ。"""
    remaining = [len(layers)]

    def release(obj=None):
        remaining[0] -= 1
        if remaining[0] == 0:
            workspace.cleanup()

    if not layers:
        workspace.cleanup()
    for layer in layers:
        layer.destroyed.connect(release)
```

3-d. `_finish` を次に置き換える。ベクタ・ラスタとも GUI で生成し、一時モードでは追加できたレイヤー全部に寿命を委ねる。

```python
def _finish(task):
    """GUIスレッドでレイヤーを追加する。取消済み・置き換えられたタスクの結果は捨てる。"""
    result = task.result
    workspace = result["temporary"] if result else None
    try:
        if not _is_current(task):
            return
        if task.isCanceled():
            return
        if task.error is not None:
            notify(f"レイヤーを追加できません: {task.error}", warning=True)
            return
        if result is None:
            return
        added, failed = [], []
        for provider, source, title in result["layers"]:
            layer_type = QgsRasterLayer if provider == "gdal" else QgsVectorLayer
            layer = layer_type(source, title, provider)
            if not layer.isValid():
                failed.append(title)
                continue
            QgsProject.instance().addMapLayer(layer)
            added.append(layer)
        if failed:
            notify(f"読み込めないレイヤー: {', '.join(failed)}", warning=True)
        if workspace:
            # 一時ファイルは、参照するレイヤーがすべて閉じられるまで保つ。
            _release_when_closed(workspace, added)
            workspace = None
    finally:
        if workspace:
            workspace.cleanup()
        _unregister(task)
```

3-e. `LayerLoadTask` を次に置き換える（`feedback` と `cancel()` を削除、docstring を更新）。

```python
class LayerLoadTask(QgsTask):
    """取得を取消可能なタスクで実行し、完了時にGUIでレイヤーを追加する。"""

    def __init__(self, key, name):
        super().__init__(f"国土数値情報: {name}", QgsTask.Flag.CanCancel)
        self.key, self.name = key, name
        self.result, self.error = None, None

    def run(self):
        url, member, mode, directory = self.key
        try:
            self.result = prepare(self, url, member, self.name, mode, directory)
            return True
        except Exception as exc:
            # ワーカーのQtオブジェクトを例外のtraceback経由でGUIへ持ち込まない。
            self.error = str(exc)
            return False

    def finished(self, success):
        _finish(self)
        self.result = None
```

- [x] **Step 4: 対象テストを実行して通ることを確かめる**

Run:

```bash
source setup_qgis_env.sh && .venv/bin/python -m pytest tests/test_lazy_loading.py -v -k "setting_change or context_menu or drag_fetches or temporary_vector or temporary_raster or sublayers_share or multilayer_file or cancel_task or reuses_saved"
```

Expected: すべて PASS。

- [x] **Step 5: 関連するテストファイル全体と Lint を通す**

Run:

```bash
source setup_qgis_env.sh && .venv/bin/python -m pytest tests/test_lazy_loading.py tests/test_loading_indicator.py -v
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Expected: すべて PASS。Ruff の指摘なし（未使用 import が残っていれば削除する）。`ruff format --check` が差分を出したら `.venv/bin/ruff format .` を実行する。

- [x] **Step 6: コミット**

```bash
git add ksj/layer_loading.py tests/test_lazy_loading.py
git commit -m "feat: 一時ベクタレイヤーをメモリ複製から一時ファイル参照に変更

materialize によるメモリ複製をやめ、ラスタと同じく取得した一時ファイルを参照する。
一時ディレクトリは、そこから生成したレイヤーがすべて閉じられた時点で削除する。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc"
```

---

### Task 2: 一時ディレクトリの削除失敗を警告ログに留める

**Files:**
- Modify: `ksj/layer_loading.py`（import、`_release_when_closed`、`_finish` の `finally`、`_cleanup` 追加）
- Test: `tests/test_lazy_loading.py`

**Interfaces:**
- Consumes: Task 1 の `_release_when_closed(workspace, layers)` と `_finish` の `finally`。
- Produces: `_cleanup(workspace: tempfile.TemporaryDirectory) -> None`：`workspace.cleanup()` を呼び、`OSError` は `QgsMessageLog.logMessage(message, "KSJ", Qgis.MessageLevel.Warning)` に記録して握りつぶす。`_release_when_closed` と `_finish` は `workspace.cleanup()` の代わりにこれを使う。

- [x] **Step 1: 失敗するテストを書く**

`tests/test_lazy_loading.py` の `test_cancel_task_prevents_late_layer_addition` の直後に追加する。`_cleanup` 経由で呼ぶ理由: `destroyed` スロット内で例外を発生させると PyQt が qFatal で停止する場合があり、赤のテストが「失敗」ではなく「異常終了」になるのを避ける。

```python
def test_workspace_cleanup_failure_is_logged_not_raised(qgis_app, monkeypatch):
    logged = []
    monkeypatch.setattr(
        layer_loading,
        "QgsMessageLog",
        SimpleNamespace(logMessage=lambda *args: logged.append(args)),
    )

    def fail():
        raise OSError("使用中のため削除できません")

    workspace = SimpleNamespace(name="/tmp/ksj-layer-test", cleanup=fail)
    layer_loading._cleanup(workspace)
    assert len(logged) == 1
    message, tag, level = logged[0]
    assert "使用中のため削除できません" in message and "ksj-layer-test" in message
    assert tag == "KSJ"
```

- [x] **Step 2: テストが失敗することを確かめる**

Run:

```bash
source setup_qgis_env.sh && .venv/bin/python -m pytest tests/test_lazy_loading.py -v -k cleanup_failure
```

Expected: `AttributeError: module 'ksj.layer_loading' has no attribute '_cleanup'` で FAIL。

- [x] **Step 3: `_cleanup` を実装し、呼び出し側を差し替える**

3-a. import に `Qgis` と `QgsMessageLog` を加える。

```python
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsMessageLog,
    QgsMimeDataUtils,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsTask,
    QgsVectorLayer,
)
```

3-b. `_release_when_closed` の直前に `_cleanup` を追加する。

```python
def _cleanup(workspace):
    """レイヤー破棄のスロット内で例外を出さない。失敗分はOSの一時領域掃除に任せる。"""
    try:
        workspace.cleanup()
    except OSError as exc:
        QgsMessageLog.logMessage(
            f"一時ファイルを削除できません: {workspace.name} ({exc})",
            "KSJ",
            Qgis.MessageLevel.Warning,
        )
```

3-c. `_release_when_closed` の 2 箇所の `workspace.cleanup()` を `_cleanup(workspace)` に変える。

```python
def _release_when_closed(workspace, layers):
    """一時ディレクトリを、そこから生成したレイヤーがすべて閉じられるまで保つ。"""
    remaining = [len(layers)]

    def release(obj=None):
        remaining[0] -= 1
        if remaining[0] == 0:
            _cleanup(workspace)

    if not layers:
        _cleanup(workspace)
    for layer in layers:
        layer.destroyed.connect(release)
```

3-d. `_finish` の `finally` を変える。

```python
    finally:
        if workspace:
            _cleanup(workspace)
        _unregister(task)
```

`prepare` の例外経路（ワーカー側）の `temporary.cleanup()` はそのままにする。ワーカーでは例外がそのまま `LayerLoadTask.run` で捕まえられ、利用者に通知されるため握りつぶす必要がない。

- [x] **Step 4: テストと Lint を通す**

Run:

```bash
source setup_qgis_env.sh && .venv/bin/python -m pytest tests/test_lazy_loading.py -v
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Expected: すべて PASS。Ruff の指摘なし。

- [x] **Step 5: コミット**

```bash
git add ksj/layer_loading.py tests/test_lazy_loading.py
git commit -m "fix: 一時ディレクトリの削除失敗を警告ログに留める

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc"
```

---

### Task 3: 設定ダイアログと README の説明を更新し、全体を検証する

**Files:**
- Modify: `ksj/local_storage.py:94-98`（`LoadingSettingsDialog.__init__` の `note`）
- Modify: `README.md:32`
- Modify: `docs/superpowers/plans/2026-10-24-temporary-vector-file-reference.md`（チェックボックス更新のみ）

**Interfaces:**
- Consumes: なし（文言のみ）。
- Produces: なし。

- [x] **Step 1: 設定ダイアログの説明文を変える**

`ksj/local_storage.py` の `note = QLabel(...)` を次にする。

```python
        note = QLabel(
            "ダブルクリックやドラッグで追加するときに、この設定を使います。\n"
            "一時レイヤーは一時ファイルを参照し、レイヤーを閉じると削除します。"
            "残す場合は別途保存してください。"
        )
```

- [x] **Step 2: README の説明文を変える**

`README.md` の「**一時レイヤーとして追加**」の行を次にする。

```markdown
- **一時レイヤーとして追加**: ベクタ・ラスタとも取得したファイルを一時フォルダに置き、そのまま参照します。保存先フォルダの指定は不要です。同じファイルから追加したレイヤーをすべて閉じると一時フォルダを削除します。**プロジェクト保存だけでは一時データは残りません。** 残したいレイヤーは別途ファイルへ保存してください。
```

- [x] **Step 3: 設定ダイアログのテストと Lint を通す**

Run:

```bash
source setup_qgis_env.sh && .venv/bin/python -m pytest tests/test_lazy_loading.py -v -k "settings_dialog or browser_displays"
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Expected: PASS。Ruff の指摘なし。

- [x] **Step 4: コミット**

```bash
git add ksj/local_storage.py README.md
git commit -m "docs: 一時レイヤーの説明を一時ファイル参照に合わせて更新

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc"
```

- [x] **Step 5: Docker で全テストを実行する**

Run:

```bash
bash scripts/test-docker.sh
```

Expected: 全テスト PASS。カバレッジは `ksj/layer_loading.py` の新規行（`_release_when_closed`、`_cleanup`）が網羅されていること。

- [x] **Step 6: Qt6 互換チェックを実行する**

Run:

```bash
docker run --rm --pull always --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --workdir /workspace/ -v "$(pwd):/workspace/" \
  ghcr.io/qgis/pyqgis4-checker:main-ubuntu \
  pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log .
git diff --stat
```

Expected: `pyqt6_checker.log` に `ksj/layer_loading.py` の新規指摘がない（dry run は常に終了コード 0 なのでログを読む）。`git diff --stat` が空（`--dry_run` でファイルが書き換わっていない）。

- [x] **Step 7: 計画のチェックボックスを更新してコミットする**

```bash
git add docs/superpowers/plans/2026-10-24-temporary-vector-file-reference.md
git commit -m "docs: 一時ベクタレイヤーの実装計画を完了済みに更新

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc"
```

---

## 完了条件

- 一時モードで追加したベクタは `providerType() == "ogr"` で、`source()` が `ksj-layer-*` 配下のファイルを指す。
- 同じ一時ディレクトリから生成したレイヤーをすべて閉じると、ディレクトリが削除される。1 つでも残っていれば削除しない。
- 取消・エラー・置き換え時に `ksj-layer-*` が残らない。
- 削除失敗は `QgsMessageLog` の「KSJ」タグに警告として残り、例外にならない。
- `ksj/layer_loading.py` に `materialize`、`QgsProcessingContext`、`QgsFeedback` の参照がない。
- Docker 全テスト、Ruff、pyqgis4-checker が通る。
- `imgs/loading-settings.png` の差し替えは、PR で実機スクリーンショットの更新を依頼する。
