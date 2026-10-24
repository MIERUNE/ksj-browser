# kumoy へアップロードする追加方法（PR 3）実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「追加方法・保存先」に「kumoy にアップロードして追加」を加える。必要なファイルを一時ディレクトリへ取得し、Shapefile はプレビュー付きで文字コードを確認してから kumoy の Processing ダイアログへ渡し、完了後に kumoy のレイヤーを地図へ追加して一時ディレクトリを削除する。kumoy プラグインが無ければ確認のうえその場でインストールする。

**Architecture:** 新モジュール `ksj/kumoy_upload.py` が kumoy への依存（プロバイダ ID、アルゴリズム ID、セッショントークンの設定キー、公式リポジトリのパッケージ名）を一手に持つ。`local_storage` の追加方法に `"kumoy"` を加え、`layer_loading` と `mesh_index` は取得後のレイヤー一覧と一時ディレクトリを `kumoy_upload.upload_layers()` に渡す。`encoding_check` に確認ダイアログ `confirm_encoding()` を足す。kumoy の内部モジュールは import しない。

**Tech Stack:** Python 3.9 互換、PyQGIS（`qgis.core` / `qgis.gui` / `qgis.PyQt`）、QGIS 同梱の `processing` と `pyplugin_installer`、pytest + pytest-qgis、Ruff、Docker（`qgis/qgis:3.44` / `4.0-trixie` / `4.2-trixie`）

**Spec:** `docs/superpowers/specs/2026-10-24-kumoy-destination-design.md`（「実装の分割」の 3 番目）

**前提:** PR 1（`2026-10-24-encoding-detection.md`）と PR 2（`2026-10-24-mesh-index-loading-modes.md`）が完了していること。`messages.main_window`、`temporary_files`、`encoding_check.detect_shapefile_encoding / is_shapefile_layer / source_path`、`mesh_index._finish_loading(..., mode, workspace)`、`conftest.temp_root`、`helpers.workspaces / make_shapefile / shapefile_entries` を使う。

## Global Constraints

- 対応バージョンは QGIS 3.44 以上 4.x まで（Qt 5 / Qt 6 両対応）。Qt は `qgis.PyQt` 経由、enum は修飾付き。フィールド型の比較は `field.type() == QMetaType.Type.QString`（QGIS 3.44 で確認済み）。
- Python 3.9 互換。外部依存なし。パッケージ内は相対インポート。`processing` と `pyplugin_installer` は関数内で import する（ヘッドレスや起動直後に import できないため）。
- kumoy 側への依存は設計書の表のとおり。プロバイダ ID `kumoy`、`kumoy:uploadvector`（`INPUT` → `VECTOR_ID`）、`kumoy:uploadraster`（`INPUT` → `RASTER_ID`）、`kumoy:addvectortomap`（`VECTOR_ID`）、`kumoy:addrastertomap`（`RASTER_ID`）、`QSettings` の `Kumoy/session_token`、パッケージ `kumoy_qgis_plugin`、`metadata.txt` の name `Kumoy`、公式サイト `https://www.kumoy.io/`。
- 通知文言は設計書のとおり（本計画の定数に写してある）。
- 文言・docstring・コメント・コミットメッセージは日本語。Conventional Commits。
- 各タスクの最後に `uv run --no-sync ruff check .` と `uv run --no-sync ruff format .`（`uv.lock` が変わったら `git checkout uv.lock`）。
- クイック確認は `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest <対象> -q`、公式確認は Docker。
- コミットメッセージ末尾に次の 2 行を付ける。

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
```

---

## ファイル構成

| ファイル | 役割 |
| --- | --- |
| `ksj/kumoy_upload.py`（新規） | 定数、`is_available` `is_logged_in` `ready` `ensure_available` `installed_package` `confirm` `enable` `install`、`upload_layers` `upload` `processing_module` |
| `ksj/encoding_check.py` | `string_fields` `preview_rows` `EncodingDialog` `confirm_encoding` を追加 |
| `ksj/local_storage.py` | 追加方法 `"kumoy"`、設定ダイアログの 3 つ目のラジオとリンク、OK 時の `ensure_available` |
| `ksj/catalog_browser.py` | 先頭項目の表示文言 |
| `ksj/layer_loading.py` | `start` の事前確認、`prepare` の一時ディレクトリ条件、`_finish` の分岐 |
| `ksj/mesh_index.py` | `load_mesh` の事前確認、`_finish_loading` の分岐 |
| `tests/test_kumoy_upload.py`（新規）、既存テストへの追加 | 検証 |
| `README.md`、`imgs/loading-settings.png`、`imgs/browser-loading-mode.png` | 説明と画像 |

---

### Task 1: kumoy プラグインの確認・インストール支援・ログイン確認

**Files:**
- Create: `ksj/kumoy_upload.py`
- Create: `tests/test_kumoy_upload.py`

**Interfaces:**
- Produces: `kumoy_upload.KUMOY_URL`、`PROVIDER_ID`、`PACKAGE_NAME`、`PLUGIN_NAME`、`TOKEN_KEY`、`LOGIN_MESSAGE`、`INSTALL_PROMPT`、`ENABLE_PROMPT`、`MANUAL_INSTALL_MESSAGE`、`is_available() -> bool`、`is_logged_in() -> bool`、`ready(parent=None) -> bool`、`ensure_available(parent=None) -> bool`、`installed_package() -> str | None`、`confirm(parent, title, text) -> bool`、`enable(package) -> None`、`install() -> None`
- Consumes: PR 1 の `messages.log_message / notify / main_window`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_kumoy_upload.py` を作成する。

```python
"""kumoy プラグインの確認・インストール支援と、取得したレイヤーのアップロード。"""

import sys
import types
from types import SimpleNamespace

import pytest
from qgis import utils
from qgis.core import QgsApplication, QgsProcessingProvider, QgsSettings
from qgis.PyQt.QtCore import QSettings

from ksj import kumoy_upload


class FakeKumoyProvider(QgsProcessingProvider):
    """kumoy の Processing プロバイダが登録されている状態を作る。"""

    def id(self):
        return "kumoy"

    def name(self):
        return "Kumoy"

    def loadAlgorithms(self):
        pass


@pytest.fixture
def kumoy_provider(qgis_app):
    provider = FakeKumoyProvider()
    registry = QgsApplication.processingRegistry()
    assert registry.addProvider(provider)
    yield provider
    registry.removeProvider(provider)


@pytest.fixture
def token_key(monkeypatch):
    """kumoy の実設定に触れないよう、トークンの保存先を試験用キーにする。"""
    key = "ksj-tests/kumoy-token"
    monkeypatch.setattr(kumoy_upload, "TOKEN_KEY", key)
    QSettings().remove(key)
    yield key
    QSettings().remove(key)


@pytest.fixture
def notifications(monkeypatch):
    messages = []
    monkeypatch.setattr(
        kumoy_upload, "notify", lambda message, warning=False: messages.append(message)
    )
    return messages


def availability(monkeypatch, *answers):
    """is_available の戻り値を呼び出し順に差し替える。"""
    remaining = list(answers)
    monkeypatch.setattr(kumoy_upload, "is_available", lambda: remaining.pop(0))


def test_unavailable_without_kumoy_provider(qgis_app):
    assert not kumoy_upload.is_available()


def test_available_when_kumoy_provider_is_registered(kumoy_provider):
    assert kumoy_upload.is_available()
    assert kumoy_upload.ensure_available() is True


def test_ready_requires_login_token(kumoy_provider, token_key, notifications):
    assert kumoy_upload.ready() is False
    assert notifications == [kumoy_upload.LOGIN_MESSAGE]
    QSettings().setValue(token_key, "session")
    assert kumoy_upload.ready() is True


def test_ready_is_false_when_plugin_stays_unavailable(monkeypatch, notifications):
    monkeypatch.setattr(kumoy_upload, "ensure_available", lambda parent=None: False)
    assert kumoy_upload.ready() is False
    assert notifications == []


def test_disabled_plugin_is_enabled_after_confirmation(monkeypatch):
    availability(monkeypatch, False, True)
    monkeypatch.setattr(kumoy_upload, "installed_package", lambda: "kumoy_qgis_plugin")
    asked, enabled = [], []
    monkeypatch.setattr(
        kumoy_upload, "confirm", lambda parent, title, text: asked.append(text) or True
    )
    monkeypatch.setattr(kumoy_upload, "enable", enabled.append)
    monkeypatch.setattr(
        kumoy_upload, "install", lambda: pytest.fail("インストール済みなら取得しない")
    )
    assert kumoy_upload.ensure_available() is True
    assert asked == [kumoy_upload.ENABLE_PROMPT]
    assert enabled == ["kumoy_qgis_plugin"]


def test_missing_plugin_is_installed_after_confirmation(monkeypatch):
    availability(monkeypatch, False, True)
    monkeypatch.setattr(kumoy_upload, "installed_package", lambda: None)
    asked, installed = [], []
    monkeypatch.setattr(
        kumoy_upload, "confirm", lambda parent, title, text: asked.append(text) or True
    )
    monkeypatch.setattr(kumoy_upload, "install", lambda: installed.append(True))
    assert kumoy_upload.ensure_available() is True
    assert asked == [kumoy_upload.INSTALL_PROMPT]
    assert installed == [True]
    assert kumoy_upload.KUMOY_URL in kumoy_upload.INSTALL_PROMPT


def test_declined_installation_leaves_plugin_unavailable(monkeypatch):
    availability(monkeypatch, False, False)
    monkeypatch.setattr(kumoy_upload, "installed_package", lambda: None)
    monkeypatch.setattr(kumoy_upload, "confirm", lambda parent, title, text: False)
    monkeypatch.setattr(
        kumoy_upload, "install", lambda: pytest.fail("断られたら取得しない")
    )
    assert kumoy_upload.ensure_available() is False


def test_installed_package_is_found_by_metadata_name(monkeypatch):
    monkeypatch.setattr(utils, "updateAvailablePlugins", lambda: None)
    monkeypatch.setattr(utils, "available_plugins", ["other", "kumoy_dev"])
    monkeypatch.setattr(
        utils,
        "pluginMetadata",
        lambda package, key: {"kumoy_dev": "Kumoy"}.get(package, "Other"),
    )
    assert kumoy_upload.installed_package() == "kumoy_dev"
    monkeypatch.setattr(utils, "available_plugins", ["other"])
    assert kumoy_upload.installed_package() is None


def test_enable_loads_starts_and_remembers_plugin(monkeypatch):
    calls = []
    monkeypatch.setattr(
        utils, "loadPlugin", lambda package: calls.append(("load", package)) or True
    )
    monkeypatch.setattr(
        utils, "startPlugin", lambda package: calls.append(("start", package)) or True
    )
    key = "PythonPlugins/kumoy_test"
    QgsSettings().remove(key)
    try:
        kumoy_upload.enable("kumoy_test")
        assert calls == [("load", "kumoy_test"), ("start", "kumoy_test")]
        assert QgsSettings().value(key, False, type=bool) is True
    finally:
        QgsSettings().remove(key)


def fake_installer(monkeypatch, available, broken=False):
    """QGIS 同梱のプラグインインストーラを差し替え、呼び出しを記録する。"""
    calls = []
    installer = SimpleNamespace(
        fetchAvailablePlugins=lambda reloadMode: calls.append(("fetch", reloadMode)),
        installPlugin=lambda key: calls.append(("install", key)),
        showPluginManagerWhenReady=lambda: calls.append(("manager",)),
    )

    def instance():
        if broken:
            raise RuntimeError("壊れたインストーラ")
        return installer

    package = types.ModuleType("pyplugin_installer")
    package.instance = instance
    data = types.ModuleType("pyplugin_installer.installer_data")
    data.plugins = SimpleNamespace(all=lambda: available)
    monkeypatch.setitem(sys.modules, "pyplugin_installer", package)
    monkeypatch.setitem(sys.modules, "pyplugin_installer.installer_data", data)
    return calls


def test_install_uses_official_repository_when_listed(monkeypatch, notifications):
    calls = fake_installer(monkeypatch, {"kumoy_qgis_plugin": {}})
    kumoy_upload.install()
    assert calls == [("fetch", False), ("install", "kumoy_qgis_plugin")]
    assert notifications == []


def test_install_opens_plugin_manager_when_not_listed(monkeypatch, notifications):
    calls = fake_installer(monkeypatch, {})
    kumoy_upload.install()
    assert calls == [("fetch", False), ("manager",)]
    assert notifications == [kumoy_upload.MANUAL_INSTALL_MESSAGE]


def test_install_failure_is_logged_and_guides_manual_install(monkeypatch, notifications):
    logged = []
    monkeypatch.setattr(
        kumoy_upload, "log_message", lambda message, warning=False: logged.append(message)
    )
    fake_installer(monkeypatch, {}, broken=True)
    kumoy_upload.install()
    assert any("壊れたインストーラ" in message for message in logged)
    assert notifications == [kumoy_upload.MANUAL_INSTALL_MESSAGE]
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_kumoy_upload.py -q`
Expected: FAIL（`ImportError: cannot import name 'kumoy_upload'`）

- [ ] **Step 3: `ksj/kumoy_upload.py` を作成する（前半）**

```python
"""kumoy プラグインの Processing アルゴリズムで、取得したレイヤーを kumoy にアップロードする。

kumoy 側への依存はこのモジュールの定数に限る。プロバイダ ID、アルゴリズム ID と
出力名、QSettings のセッショントークン、公式リポジトリのパッケージ名。
kumoy の内部モジュールは import しない。
"""

from qgis import utils
from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsRasterLayer,
    QgsSettings,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QMessageBox

from . import encoding_check, temporary_files
from .messages import log_message, main_window, notify

KUMOY_URL = "https://www.kumoy.io/"
PROVIDER_ID = "kumoy"
# 公式プラグインリポジトリ（plugins.qgis.org）での名前と、metadata.txt の name。
PACKAGE_NAME = "kumoy_qgis_plugin"
PLUGIN_NAME = "Kumoy"
# kumoy プラグインがログイン時に保存するセッショントークン。空ならログイン前。
TOKEN_KEY = "Kumoy/session_token"
# provider → (アップロード, 結果の ID 名, 地図への追加)
ALGORITHMS = {
    "ogr": ("kumoy:uploadvector", "VECTOR_ID", "kumoy:addvectortomap"),
    "gdal": ("kumoy:uploadraster", "RASTER_ID", "kumoy:addrastertomap"),
}
LOGIN_MESSAGE = "kumoy ブラウザパネルの Kumoy 項目からログインしてください。"
INSTALL_PROMPT = (
    f'kumoy へのアップロードには <a href="{KUMOY_URL}">kumoy</a> プラグインが必要です。'
    "インストールしますか？"
)
ENABLE_PROMPT = "kumoy プラグインはインストール済みですが無効です。有効化しますか？"
MANUAL_INSTALL_MESSAGE = (
    f"プラグインマネージャで「{PLUGIN_NAME}」を検索してインストールしてください。"
)
ADDED_ELSEWHERE_MESSAGE = (
    "アップロードは完了しました。"
    "kumoy ブラウザでプロジェクトを切り替えてから追加してください。"
)


def is_available():
    """kumoy の Processing プロバイダが登録済みか。インストール先フォルダ名に依存しない。"""
    return QgsApplication.processingRegistry().providerById(PROVIDER_ID) is not None


def is_logged_in():
    return bool(QSettings().value(TOKEN_KEY, ""))


def ready(parent=None):
    """追加操作の開始前に、プラグインとログインを確かめる。"""
    if not ensure_available(parent):
        return False
    if not is_logged_in():
        notify(LOGIN_MESSAGE, warning=True)
        return False
    return True


def ensure_available(parent=None):
    """未インストール・無効なら利用者の了承を得て整える。整った場合だけ True。"""
    if is_available():
        return True
    if parent is None:
        parent = main_window()
    package = installed_package()
    if package:
        if confirm(parent, "kumoy プラグインの有効化", ENABLE_PROMPT):
            enable(package)
    elif confirm(parent, "kumoy プラグインのインストール", INSTALL_PROMPT):
        install()
    return is_available()


def installed_package():
    """インストール済みだが読み込まれていない kumoy のパッケージ名。なければ None。"""
    utils.updateAvailablePlugins()
    for package in utils.available_plugins:
        if utils.pluginMetadata(package, "name") == PLUGIN_NAME:
            return package
    return None


def confirm(parent, title, text):
    # QMessageBox はリッチテキストのリンクを既定で外部ブラウザで開く。
    answer = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def enable(package):
    if utils.loadPlugin(package) and utils.startPlugin(package):
        QgsSettings().setValue(f"PythonPlugins/{package}", True)


def install():
    """公式リポジトリから取得する。一覧に無い・失敗した場合は手動インストールを案内する。"""
    try:
        from pyplugin_installer import instance
        from pyplugin_installer.installer_data import plugins

        installer = instance()
        installer.fetchAvailablePlugins(reloadMode=False)
        if PACKAGE_NAME in plugins.all():
            installer.installPlugin(PACKAGE_NAME)
            return
        installer.showPluginManagerWhenReady()
    except Exception as exc:
        # QGIS 内部のインストーラ API に頼るため、失敗は手動インストールへ切り替える。
        log_message(
            f"kumoy プラグインのインストールを開始できません: {exc}", warning=True
        )
    notify(MANUAL_INSTALL_MESSAGE, warning=True)
```

`QgsProject` `QgsRasterLayer` `QgsVectorLayer` `encoding_check` `temporary_files` は Task 4 で使う。Ruff の未使用 import を避けるため、この時点では import 行をまだ書かず、Task 4 で追加してもよい。

- [ ] **Step 4: テストと lint を通す**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_kumoy_upload.py -q`
Expected: PASS

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format .`
Expected: エラーなし

- [ ] **Step 5: コミット**

```bash
git add ksj/kumoy_upload.py tests/test_kumoy_upload.py
git commit -q -F - <<'EOF'
feat: kumoy プラグインの有無・ログイン状態の確認とインストール支援

Processing プロバイダの登録でプラグインを判定し、未インストールなら確認のうえ
QGIS のプラグインインストーラで公式リポジトリから取得する。無効なら有効化する。
ログイン状態は kumoy のセッショントークンの有無で判定する。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 2: 追加方法「kumoy」の設定とブラウザ表示

**Files:**
- Modify: `ksj/local_storage.py`（`loading_mode`、`LoadingSettingsDialog.__init__` と `accept`）
- Modify: `ksj/catalog_browser.py`（`KsjLoadingSettingsItem.update_label`）
- Test: `tests/test_lazy_loading.py`

**Interfaces:**
- Produces: `local_storage.MODES = ("save", "temporary", "kumoy")`、`loading_mode()` が `"kumoy"` を返しうる、`LoadingSettingsDialog.kumoy`（`QRadioButton`）、`LoadingSettingsDialog.selected_mode() -> str`
- Consumes: Task 1 の `kumoy_upload.ensure_available`、`kumoy_upload.KUMOY_URL`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_lazy_loading.py` の `test_settings_dialog_remembers_temporary_and_cancel_is_atomic` の直後に追加する。冒頭の import に `from qgis.PyQt.QtWidgets import QLabel` を加える（既存の `QApplication, QMenu, QRadioButton` と同じ行）。

```python
def test_settings_dialog_keeps_open_until_kumoy_is_available(
    storage_settings, monkeypatch
):
    QgsSettings().setValue(local_storage.MODE_KEY, "temporary")
    answers, asked, states = [False, True], [], []

    def ensure_available(parent=None):
        asked.append(parent is not None)
        return answers.pop(0)

    monkeypatch.setattr(local_storage.kumoy_upload, "ensure_available", ensure_available)

    def choose_kumoy():
        dialog = QApplication.activeModalWidget()
        assert any(
            "https://www.kumoy.io/" in label.text()
            for label in dialog.findChildren(QLabel)
        )
        dialog.kumoy.setChecked(True)
        dialog.accept()
        # 1 回目はプラグインが整わず、閉じずに設定も変えない。
        states.append((dialog.isVisible(), local_storage.loading_mode()))
        dialog.accept()

    QTimer.singleShot(0, choose_kumoy)
    assert local_storage.configure_loading()
    assert states == [(True, "temporary")]
    assert local_storage.loading_mode() == "kumoy"
    assert asked == [True, True]
```

`test_browser_displays_current_preference_and_updates_after_dialog` の引数に `monkeypatch` を加え、末尾に追加する。

```python
    monkeypatch.setattr(
        local_storage.kumoy_upload, "ensure_available", lambda parent=None: True
    )

    def choose_kumoy():
        dialog = QApplication.activeModalWidget()
        dialog.kumoy.setChecked(True)
        dialog.accept()

    QTimer.singleShot(0, choose_kumoy)
    assert item.handleDoubleClick()
    qgis_app.processEvents()
    assert "kumoy にアップロード" in item.name() and "保存しない" in item.name()
    assert "https://www.kumoy.io/" in item.toolTip()
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lazy_loading.py -k "kumoy or displays_current_preference" -q`
Expected: FAIL（`AttributeError: module 'ksj.local_storage' has no attribute 'kumoy_upload'`）

- [ ] **Step 3: `local_storage` を実装する**

- `from .messages import main_window` の行の前に `from . import kumoy_upload` を加える（`kumoy_upload` は `local_storage` を import しないため循環しない）。
- `loading_mode` を次にする。

```python
MODES = ("save", "temporary", "kumoy")


def loading_mode() -> str:
    """既存利用者は保存方式を引き継ぐ。設定は追加操作のたびに参照する。"""
    value = QgsSettings().value(MODE_KEY, "save", type=str)
    return value if value in MODES else "save"
```

- `LoadingSettingsDialog.__init__` の `layout.addWidget(self.temporary)` の直後に追加する。

```python
        self.kumoy = QRadioButton("kumoy にアップロードして追加")
        kumoy_row = QHBoxLayout()
        kumoy_row.addWidget(self.kumoy)
        about = QLabel(f'<a href="{kumoy_upload.KUMOY_URL}">kumoy について</a>')
        about.setOpenExternalLinks(True)
        about.setToolTip(kumoy_upload.KUMOY_URL)
        kumoy_row.addWidget(about)
        kumoy_row.addStretch()
        layout.addLayout(kumoy_row)
```

- `note` の文言を次にする。

```python
        note = QLabel(
            "ダブルクリックやドラッグで追加するときに、この設定を使います。\n"
            "一時レイヤーは一時ファイルを参照し、レイヤーを閉じると削除します。"
            "残す場合は別途保存してください。\n"
            "kumoy へは必要なファイルを一時フォルダへ取得してアップロードし、"
            "完了後に一時フォルダを削除します。Shapefile は文字コードを確認してから送ります。"
        )
```

- `self.temporary.setChecked(mode == "temporary")` の直後に `self.kumoy.setChecked(mode == "kumoy")` を加える。
- `accept` を次にする。

```python
    def accept(self):
        if self.save.isChecked():
            if not self.directory.text().strip():
                QMessageBox.warning(
                    self, "保存先が未設定です", "保存先フォルダを選択してください。"
                )
                return
            if _remember_directory(self.directory.text(), self) is None:
                return
        elif self.kumoy.isChecked() and not kumoy_upload.ensure_available(self):
            # プラグインが整わなければ閉じず、設定も変えない。
            return
        QgsSettings().setValue(MODE_KEY, self.selected_mode())
        loading_settings_signals.changed.emit()
        super().accept()

    def selected_mode(self):
        if self.save.isChecked():
            return "save"
        return "kumoy" if self.kumoy.isChecked() else "temporary"
```

- [ ] **Step 4: ブラウザ表示を実装する**

`ksj/catalog_browser.py` の `from . import catalog, layer_loading, local_storage, remote_zip, zip_scanner` に `kumoy_upload` を加え、`KsjLoadingSettingsItem.update_label` を次にする。

```python
    @pyqtSlot()
    def update_label(self):
        mode = local_storage.loading_mode()
        directory = local_storage.download_directory()
        hint = "\nダブルクリックで追加方法・保存先を変更"
        if mode == "kumoy":
            title = "追加方法: kumoy にアップロード（ローカルに保存しない）"
            hint = f"\n{kumoy_upload.KUMOY_URL}{hint}"
        elif mode == "temporary":
            title = "追加方法: 一時レイヤー（フォルダに保存しない）"
        elif directory:
            title = f"追加方法: 保存して追加 — {directory}"
        else:
            title = "追加方法: 保存して追加（保存先未設定）"
        self.setName(title)
        self.setToolTip(title + hint)
```

- [ ] **Step 5: テストと lint を通す**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lazy_loading.py tests/test_local_storage.py tests/test_catalog_browser.py -q`
Expected: PASS

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format .`
Expected: エラーなし

- [ ] **Step 6: コミット**

```bash
git add ksj/local_storage.py ksj/catalog_browser.py tests/test_lazy_loading.py
git commit -q -F - <<'EOF'
feat: 追加方法に「kumoy にアップロードして追加」を加える

設定画面に 3 つ目の方式と kumoy へのリンクを置き、選択時に kumoy プラグインの
有無を確かめる。ブラウザ先頭の項目にも現在の方式を表示する。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 3: 文字コード確認ダイアログ（`encoding_check.confirm_encoding`）

**Files:**
- Modify: `ksj/encoding_check.py`（import と末尾に追加）
- Test: `tests/test_encoding_check.py`

**Interfaces:**
- Produces: `encoding_check.ENCODING_CHOICES = ("UTF-8", "Shift_JIS", "EUC-JP")`、`PREVIEW_ROWS = 5`、`DIALOG_TITLE`、`string_fields(layer) -> list[QgsField]`、`preview_rows(layer, fields) -> list[list[str]]`、`EncodingDialog(layer, detection, parent=None)`（`objectName` は `ksj-encoding`、根拠ラベルの `objectName` は `ksj-encoding-reason`、属性 `encoding: QComboBox`、`preview: QTableWidget`）、`confirm_encoding(layer, parent=None) -> bool`（OK ならレイヤーに文字コードを設定済みで True。文字列フィールドが無ければダイアログを出さず True。キャンセルは False）
- Consumes: PR 1 の `detect_shapefile_encoding`、`source_path`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_encoding_check.py` の冒頭 import を次のように増やす。

```python
import pytest
from qgis.core import QgsVectorLayer
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
)

from ksj import encoding_check
from tests.helpers import make_shapefile, make_vector, point_file
```

末尾に追加する。

```python
def interact_with_dialog(action):
    """文字コード確認ダイアログが開いたら action(dialog) を実行する。"""

    def attempt():
        dialog = QApplication.activeModalWidget()
        if dialog is None or dialog.objectName() != "ksj-encoding":
            QTimer.singleShot(10, attempt)
            return
        action(dialog)

    QTimer.singleShot(0, attempt)


def test_confirm_encoding_previews_and_keeps_chosen_encoding(qgis_app, tmp_path):
    path = make_shapefile(tmp_path / "city.shp", TEXTS, "cp932")
    layer = QgsVectorLayer(str(path), "city", "ogr")
    seen = {}

    def interact(dialog):
        table = dialog.findChild(QTableWidget)
        combo = dialog.findChild(QComboBox)
        seen["initial"] = (combo.currentText(), table.item(0, 0).text(), table.rowCount())
        seen["reason"] = dialog.findChild(QLabel, "ksj-encoding-reason").text()
        combo.setCurrentText("UTF-8")
        seen["utf8"] = table.item(0, 0).text()
        combo.setCurrentText("Shift_JIS")
        buttons = dialog.findChild(QDialogButtonBox)
        seen["ok"] = buttons.button(QDialogButtonBox.StandardButton.Ok).text()
        buttons.button(QDialogButtonBox.StandardButton.Ok).click()

    interact_with_dialog(interact)
    assert encoding_check.confirm_encoding(layer) is True
    assert seen["initial"] == ("Shift_JIS", "札幌市中央区", 2)
    assert seen["reason"] == encoding_check.REASON_BYTES
    assert seen["utf8"] != "札幌市中央区"
    assert seen["ok"] == "この内容でアップロード"
    assert layer.dataProvider().encoding() == "Shift_JIS"
    assert [feature["name"] for feature in layer.getFeatures()] == TEXTS


def test_confirm_encoding_cancel_returns_false(qgis_app, tmp_path):
    path = make_shapefile(tmp_path / "city.shp", TEXTS, "cp932")
    layer = QgsVectorLayer(str(path), "city", "ogr")
    interact_with_dialog(lambda dialog: dialog.reject())
    assert encoding_check.confirm_encoding(layer) is False


def test_undetermined_encoding_warns_and_defaults_to_utf8(qgis_app, tmp_path):
    path = make_shapefile(tmp_path / "city.shp", ["Sapporo"], "ascii")
    layer = QgsVectorLayer(str(path), "city", "ogr")
    seen = {}

    def interact(dialog):
        seen["combo"] = dialog.findChild(QComboBox).currentText()
        seen["reason"] = dialog.findChild(QLabel, "ksj-encoding-reason").text()
        dialog.accept()

    interact_with_dialog(interact)
    assert encoding_check.confirm_encoding(layer) is True
    assert seen["combo"] == "UTF-8"
    assert encoding_check.UNDETERMINED in seen["reason"]


def test_confirm_encoding_skips_dialog_without_string_fields(
    qgis_app, tmp_path, monkeypatch
):
    path = make_vector(tmp_path / "points.shp", ["points"], driver="ESRI Shapefile")
    layer = QgsVectorLayer(str(path), "points", "ogr")
    monkeypatch.setattr(
        encoding_check,
        "EncodingDialog",
        lambda *args: pytest.fail("文字列フィールドが無ければ確認しない"),
    )
    assert encoding_check.confirm_encoding(layer) is True
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_encoding_check.py -k confirm_encoding -q`
Expected: FAIL（`AttributeError: ... has no attribute 'confirm_encoding'`）

- [ ] **Step 3: ダイアログを実装する**

`ksj/encoding_check.py` の import を次のように増やす。

```python
import struct
from collections import namedtuple
from pathlib import Path

from qgis.core import Qgis, QgsFeatureRequest
from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .messages import log_message
```

定数の末尾（`Detection = ...` の前）に追加する。

```python
# ダイアログで選べる文字コード。EUC-JP は国土数値情報に無いため自動判定しない。
ENCODING_CHOICES = (UTF8, SHIFT_JIS, "EUC-JP")
PREVIEW_ROWS = 5
DIALOG_TITLE = "kumoy へアップロードする前に文字コードを確認"
```

ファイル末尾に追加する。

```python
def string_fields(layer):
    return [
        field for field in layer.fields() if field.type() == QMetaType.Type.QString
    ]


def preview_rows(layer, fields):
    """先頭地物の文字列属性。ジオメトリは読まない。"""
    names = [field.name() for field in fields]
    request = (
        QgsFeatureRequest()
        .setFlags(Qgis.FeatureRequestFlag.NoGeometry)
        .setLimit(PREVIEW_ROWS)
        .setSubsetOfAttributes(names, layer.fields())
    )
    rows = []
    for feature in layer.getFeatures(request):
        values = [feature.attribute(name) for name in names]
        rows.append([value if isinstance(value, str) else "" for value in values])
    return rows


class EncodingDialog(QDialog):
    """文字コードを切り替えながら属性を確かめ、アップロードする文字コードを決める。"""

    def __init__(self, layer, detection, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.fields = string_fields(layer)
        self.setObjectName("ksj-encoding")
        self.setWindowTitle(DIALOG_TITLE)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(source_path(layer).name))
        reason = QLabel(detection.reason)
        reason.setObjectName("ksj-encoding-reason")
        if detection.encoding is None:
            reason.setText(f"{UNDETERMINED}。プレビューで確認してください。")
            reason.setStyleSheet("color: #b00020;")
        layout.addWidget(reason)
        row = QHBoxLayout()
        row.addWidget(QLabel("文字コード"))
        self.encoding = QComboBox()
        self.encoding.addItems(list(ENCODING_CHOICES))
        self.encoding.setCurrentText(detection.encoding or UTF8)
        row.addWidget(self.encoding)
        row.addStretch()
        layout.addLayout(row)
        self.preview = QTableWidget()
        self.preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.preview)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "この内容でアップロード"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.encoding.currentTextChanged.connect(self.apply_encoding)
        self.apply_encoding(self.encoding.currentText())
        self.resize(640, 360)

    def apply_encoding(self, encoding):
        """レイヤーの文字コードを切り替えてプレビューを引き直す。ローカルファイルなので即時。"""
        self.layer.setProviderEncoding(encoding)
        rows = preview_rows(self.layer, self.fields)
        self.preview.clear()
        self.preview.setColumnCount(len(self.fields))
        self.preview.setHorizontalHeaderLabels([field.name() for field in self.fields])
        self.preview.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column, value in enumerate(values):
                self.preview.setItem(row_index, column, QTableWidgetItem(value))


def confirm_encoding(layer, parent=None):
    """kumoy へ送る前に文字コードを利用者に確かめてもらう。OK なら True、キャンセルは False。

    文字列フィールドが無ければ文字コードは無関係なのでダイアログを出さない。
    """
    if not string_fields(layer):
        return True
    dialog = EncodingDialog(
        layer, detect_shapefile_encoding(source_path(layer)), parent
    )
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    return accepted
```

- [ ] **Step 4: テストと lint を通す**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_encoding_check.py -q`
Expected: PASS

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format .`
Expected: エラーなし

- [ ] **Step 5: コミット**

```bash
git add ksj/encoding_check.py tests/test_encoding_check.py
git commit -q -F - <<'EOF'
feat: kumoy へ送る前に文字コードをプレビュー付きで確認するダイアログ

判定した文字コードを初期値に、先頭 5 地物の文字列属性を見ながら UTF-8 /
Shift_JIS / EUC-JP を切り替えられる。取得済みのローカルファイルだけを読む。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 4: アップロード処理（`kumoy_upload.upload_layers`）

**Files:**
- Modify: `ksj/kumoy_upload.py`（末尾に追加）
- Test: `tests/test_kumoy_upload.py`

**Interfaces:**
- Produces: `kumoy_upload.upload_layers(layers, workspace, parent=None) -> None`（`layers` は `(provider, source, title)` の列。`workspace` は `temporary_files.workspace()` の戻り値か None。終了時に削除する）、`kumoy_upload.upload(layer, provider) -> None`、`kumoy_upload.processing_module()`（QGIS 同梱の `processing` を返す。テストで差し替える）、`ADDED_ELSEWHERE_MESSAGE`
- Consumes: Task 3 の `encoding_check.confirm_encoding`、PR 1 の `encoding_check.is_shapefile_layer`、`temporary_files.cleanup`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_kumoy_upload.py` の冒頭 import に `from pathlib import Path`、`from qgis.core import QgsProject, QgsVectorLayer`、`from ksj import encoding_check, temporary_files`、`from tests.helpers import make_raster, make_shapefile, point_file` を加え、末尾に追加する。

```python
@pytest.fixture
def fake_processing(monkeypatch):
    """kumoy のダイアログと地図追加を差し替え、渡されたレイヤーの状態を記録する。"""
    calls = SimpleNamespace(
        dialogs=[], loads=[], results={"VECTOR_ID": "vec-1"}, load_error=None
    )

    def exec_dialog(algorithm, parameters):
        layer = parameters["INPUT"]
        project = QgsProject.instance()
        calls.dialogs.append(
            (
                algorithm,
                layer.name(),
                project.mapLayer(layer.id()) is not None,
                project.layerTreeRoot().findLayer(layer.id()) is None,
                layer.dataProvider().encoding()
                if isinstance(layer, QgsVectorLayer)
                else None,
            )
        )
        return dict(calls.results)

    def run_and_load(algorithm, parameters):
        calls.loads.append((algorithm, parameters))
        if calls.load_error is not None:
            raise calls.load_error

    monkeypatch.setattr(
        kumoy_upload,
        "processing_module",
        lambda: SimpleNamespace(
            execAlgorithmDialog=exec_dialog, runAndLoadResults=run_and_load
        ),
    )
    return calls


@pytest.fixture
def confirmed_encoding(monkeypatch):
    """文字コード確認ダイアログを差し替え、呼ばれたレイヤー名を記録する。"""
    confirmed = []
    monkeypatch.setattr(
        encoding_check,
        "confirm_encoding",
        lambda layer, parent=None: confirmed.append(layer.name()) or True,
    )
    return confirmed


def test_upload_registers_hidden_layer_then_adds_kumoy_layer_and_cleans_workspace(
    qgis_app, qgis_new_project, tmp_path, temp_root, fake_processing, confirmed_encoding, notifications
):
    workspace = temporary_files.workspace()
    # .cpg を付けて QGIS の既定に依存せず UTF-8 で読ませる（確認ダイアログは差し替え済み）。
    path = make_shapefile(
        Path(workspace.name) / "city.shp", ["札幌市"], "utf-8", cpg="UTF-8"
    )
    kumoy_upload.upload_layers([("ogr", str(path), "city")], workspace)
    assert fake_processing.dialogs == [("kumoy:uploadvector", "city", True, True, "UTF-8")]
    assert fake_processing.loads == [("kumoy:addvectortomap", {"VECTOR_ID": "vec-1"})]
    assert confirmed_encoding == ["city"]
    assert notifications == ["kumoy にアップロードしました: city"]
    assert not QgsProject.instance().mapLayers()
    assert not Path(workspace.name).exists()


def test_upload_raster_uses_raster_algorithms(
    qgis_app, qgis_new_project, tmp_path, fake_processing, confirmed_encoding, notifications
):
    fake_processing.results = {"RASTER_ID": "ras-1"}
    path = make_raster(tmp_path / "height.tif")
    kumoy_upload.upload_layers([("gdal", str(path), "height")], None)
    assert [call[:2] for call in fake_processing.dialogs] == [("kumoy:uploadraster", "height")]
    assert fake_processing.loads == [("kumoy:addrastertomap", {"RASTER_ID": "ras-1"})]
    assert confirmed_encoding == []
    assert notifications == ["kumoy にアップロードしました: height"]


def test_geojson_is_uploaded_without_encoding_dialog(
    qgis_app, qgis_new_project, tmp_path, fake_processing, confirmed_encoding
):
    kumoy_upload.upload_layers([("ogr", str(point_file(tmp_path)), "dams")], None)
    assert confirmed_encoding == []
    assert len(fake_processing.dialogs) == 1


def test_canceled_dialog_uploads_nothing_and_still_cleans_workspace(
    qgis_app, qgis_new_project, temp_root, fake_processing, confirmed_encoding, notifications
):
    fake_processing.results = {}
    workspace = temporary_files.workspace()
    path = point_file(Path(workspace.name))
    kumoy_upload.upload_layers([("ogr", str(path), "dams")], workspace)
    assert fake_processing.loads == [] and notifications == []
    assert not QgsProject.instance().mapLayers()
    assert not Path(workspace.name).exists()


def test_canceled_encoding_dialog_skips_the_layer(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, fake_processing
):
    monkeypatch.setattr(encoding_check, "confirm_encoding", lambda layer, parent=None: False)
    path = make_shapefile(tmp_path / "city.shp", ["札幌市"], "utf-8")
    kumoy_upload.upload_layers([("ogr", str(path), "city")], None)
    assert fake_processing.dialogs == []


def test_failed_map_addition_is_reported_after_upload(
    qgis_app, qgis_new_project, tmp_path, fake_processing, confirmed_encoding, notifications
):
    fake_processing.load_error = RuntimeError("選択中のプロジェクトではありません")
    kumoy_upload.upload_layers([("ogr", str(point_file(tmp_path)), "dams")], None)
    assert notifications == [kumoy_upload.ADDED_ELSEWHERE_MESSAGE]


def test_invalid_and_failing_layers_are_reported_and_do_not_stop_others(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, fake_processing, notifications
):
    def exploding_dialog(algorithm, parameters):
        raise RuntimeError("kumoy 側の例外")

    good = point_file(tmp_path, "good.geojson")
    bad = point_file(tmp_path, "bad.geojson")
    original = kumoy_upload.processing_module
    requests = []

    def module():
        # 最初のアップロード（bad）だけ kumoy 側の例外にし、次（good）は通常どおり。
        requests.append(True)
        if len(requests) == 1:
            return SimpleNamespace(
                execAlgorithmDialog=exploding_dialog, runAndLoadResults=lambda *a: None
            )
        return original()

    monkeypatch.setattr(kumoy_upload, "processing_module", module)
    kumoy_upload.upload_layers(
        [("ogr", "/missing.geojson", "missing"), ("ogr", str(bad), "bad"), ("ogr", str(good), "good")],
        None,
    )
    assert [call[1] for call in fake_processing.dialogs] == ["good"]
    assert "kumoy へのアップロードに失敗しました: bad (kumoy 側の例外)" in notifications
    assert "読み込めないレイヤー: missing" in notifications
    assert not QgsProject.instance().mapLayers()
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_kumoy_upload.py -k upload -q`
Expected: FAIL（`AttributeError: ... has no attribute 'processing_module'` / `'upload_layers'`）

- [ ] **Step 3: 実装する**

`ksj/kumoy_upload.py` の末尾に追加する（Task 1 で import を省いた場合は `QgsProject` `QgsRasterLayer` `QgsVectorLayer` と `from . import encoding_check, temporary_files` をここで加える）。

```python
def processing_module():
    """QGIS 同梱の processing。GUI 起動後に import できるため関数内で読み込む。"""
    import processing

    return processing


def upload_layers(layers, workspace, parent=None):
    """各レイヤーを kumoy のダイアログでアップロードし、終了後に一時ディレクトリを削除する。

    layers は prepare() と同じ (provider, source, title) の列。GUI スレッドで呼ぶ。
    """
    if parent is None:
        parent = main_window()
    unreadable = []
    try:
        for provider, source, title in layers:
            layer_type = QgsRasterLayer if provider == "gdal" else QgsVectorLayer
            layer = layer_type(source, title, provider)
            if not layer.isValid():
                unreadable.append(title)
                continue
            if provider == "ogr" and encoding_check.is_shapefile_layer(layer):
                if not encoding_check.confirm_encoding(layer, parent):
                    continue
            try:
                upload(layer, provider)
            except Exception as exc:
                # kumoy 側の例外で残りのレイヤーと後片付けを止めない。
                log_message(f"kumoy へのアップロードに失敗: {title} ({exc})", warning=True)
                notify(
                    f"kumoy へのアップロードに失敗しました: {title} ({exc})", warning=True
                )
    finally:
        if workspace is not None:
            temporary_files.cleanup(workspace)
    if unreadable:
        notify(f"読み込めないレイヤー: {', '.join(unreadable)}", warning=True)


def upload(layer, provider):
    """kumoy のダイアログで 1 レイヤーをアップロードし、完了したら地図へ追加する。

    ダイアログは QgsProject に登録されたレイヤーしか INPUT に受け付けないため、
    レイヤーツリーに出さずに登録し、終了後に外す。
    """
    upload_id, result_key, add_id = ALGORITHMS[provider]
    processing = processing_module()
    project = QgsProject.instance()
    name = layer.name()
    project.addMapLayer(layer, False)
    try:
        results = processing.execAlgorithmDialog(upload_id, {"INPUT": layer}) or {}
    finally:
        # removeMapLayer はレイヤーを破棄する。以降 layer に触れない。
        project.removeMapLayer(layer.id())
    uploaded = results.get(result_key)
    if not uploaded:
        return
    try:
        processing.runAndLoadResults(add_id, {result_key: uploaded})
    except Exception as exc:
        # kumoy ブラウザで選択中のプロジェクトと違う先へ送った場合など。
        log_message(f"kumoy レイヤーを地図に追加できません: {exc}", warning=True)
        notify(ADDED_ELSEWHERE_MESSAGE, warning=True)
        return
    notify(f"kumoy にアップロードしました: {name}")
```

- [ ] **Step 4: テストと lint を通す**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_kumoy_upload.py -q`
Expected: PASS

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format .`
Expected: エラーなし

- [ ] **Step 5: コミット**

```bash
git add ksj/kumoy_upload.py tests/test_kumoy_upload.py
git commit -q -F - <<'EOF'
feat: 取得したレイヤーを kumoy のダイアログでアップロードし地図へ追加する

レイヤーツリーに出さずにプロジェクトへ登録して kumoy:uploadvector /
uploadraster の INPUT に渡し、完了後に addvectortomap / addrastertomap で
kumoy のレイヤーを追加する。終了後に一時ディレクトリを削除する。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 5: ブラウザ経路を kumoy に接続する

**Files:**
- Modify: `ksj/layer_loading.py`（import、`prepare`、`_finish`、`start`）
- Test: `tests/test_lazy_loading.py`

**Interfaces:**
- Produces: `layer_loading.TEMPORARY_MODES = {"temporary", "kumoy"}`
- Consumes: Task 1 の `kumoy_upload.ready`、Task 4 の `kumoy_upload.upload_layers`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_lazy_loading.py` の `from ksj import ...` に `temporary_files` が無ければ加え、末尾に追加する。

```python
def test_kumoy_mode_hands_fetched_files_to_upload_and_keeps_nothing(
    qgis_app, qgis_new_project, storage_settings, http_data, temp_root, monkeypatch
):
    archive_with_unselected_data(http_data)
    QgsSettings().setValue(local_storage.MODE_KEY, "kumoy")
    monkeypatch.setattr(layer_loading.kumoy_upload, "ready", lambda parent=None: True)
    uploads = []

    def upload(layers, workspace, parent=None):
        assert all(Path(source).is_file() for _, source, _ in layers)
        uploads.append([(provider, Path(source).name) for provider, source, _ in layers])
        temporary_files.cleanup(workspace)

    monkeypatch.setattr(layer_loading.kumoy_upload, "upload_layers", upload)
    assert listing(qgis_app, http_data)[0].handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    assert uploads == [[("ogr", "point.geojson")]]
    assert not QgsProject.instance().mapLayers()
    assert not workspaces(temp_root)
    assert not storage_settings.exists()


def test_kumoy_mode_does_not_fetch_without_plugin_or_login(
    qgis_app, storage_settings, http_data, monkeypatch
):
    QgsSettings().setValue(local_storage.MODE_KEY, "kumoy")
    monkeypatch.setattr(layer_loading.kumoy_upload, "ready", lambda parent=None: False)
    item = listing(qgis_app, http_data)[0]
    before = len(http_data["requests"])
    assert item.handleDoubleClick()
    assert not layer_loading.pending
    assert len(http_data["requests"]) == before
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lazy_loading.py -k kumoy_mode -q`
Expected: FAIL（`AttributeError: module 'ksj.layer_loading' has no attribute 'kumoy_upload'`）

- [ ] **Step 3: 実装する**

`ksj/layer_loading.py`:
- `from . import encoding_check, local_storage, remote_zip, temporary_files, zip_scanner` に `kumoy_upload` を加える。
- `LoadKey = ...` の直前に追加する。

```python
# 一時ディレクトリへ取得する追加方法。kumoy はアップロード後に削除する。
TEMPORARY_MODES = {"temporary", "kumoy"}
```

- `prepare` の冒頭を `temporary = temporary_files.workspace() if mode in TEMPORARY_MODES else None` にする。`saved = (... if temporary else None)` の 2 か所はそのまま（kumoy でも保存済みを再利用する）。
- `_finish` の `if result is None: return` の直後に追加する。

```python
        if task.key.mode == "kumoy":
            # 一時ディレクトリの削除はアップロード処理に委ねる。
            kumoy_upload.upload_layers(result["layers"], workspace)
            workspace = None
            return
```

- `start` の `key = LoadKey(...)` の直前に追加する。

```python
    if mode == "kumoy" and not kumoy_upload.ready():
        return
```

- [ ] **Step 4: テストと lint を通す**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lazy_loading.py tests/test_loading_indicator.py -q`
Expected: PASS

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format .`
Expected: エラーなし

- [ ] **Step 5: コミット**

```bash
git add ksj/layer_loading.py tests/test_lazy_loading.py
git commit -q -F - <<'EOF'
feat: ブラウザからの追加で kumoy へアップロードする

追加方法が kumoy のとき、プラグインとログインを確かめてから一時ディレクトリへ
取得し、取得したレイヤー一覧をアップロード処理へ渡す。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 6: メッシュ索引経路を kumoy に接続する

**Files:**
- Modify: `ksj/mesh_index.py`（import、`load_mesh`、`_finish_loading`）
- Test: `tests/test_mesh_index.py`

**Interfaces:**
- Consumes: Task 1 の `kumoy_upload.ready`、Task 4 の `kumoy_upload.upload_layers`、PR 2 の `_finish_loading(..., mode, workspace)`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_mesh_index.py` の末尾に追加する。

```python
def test_mesh_kumoy_mode_hands_selected_layers_to_upload(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, storage_settings, temp_root, layer_choices
):
    QgsSettings().setValue(local_storage.MODE_KEY, "kumoy")
    monkeypatch.setattr(mesh_index.kumoy_upload, "ready", lambda parent=None: True)
    uploads = []

    def upload(layers, workspace, parent=None):
        assert all(Path(source.split("|")[0]).is_file() for _, source, _ in layers)
        uploads.append(sorted(name for _, _, name in layers))
        temporary_files.cleanup(workspace)

    monkeypatch.setattr(mesh_index.kumoy_upload, "upload_layers", upload)
    layer_choices([0, 1])
    resource = local_resource(tmp_path, monkeypatch)
    index = mesh_index.add_mesh_index("道路", [resource])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    wait_for_loads(qgis_app)
    assert uploads == [["one", "two"]]
    assert list(QgsProject.instance().mapLayers()) == [index.id()]
    assert not workspaces(temp_root)
    assert not list(tmp_path.glob("data-*"))


def test_mesh_kumoy_mode_stops_before_fetching_when_not_ready(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, storage_settings
):
    QgsSettings().setValue(local_storage.MODE_KEY, "kumoy")
    monkeypatch.setattr(mesh_index.kumoy_upload, "ready", lambda parent=None: False)
    monkeypatch.setattr(
        mesh_index,
        "scan_resource",
        lambda *args, **kwargs: pytest.fail("準備できていなければ取得しない"),
    )
    resource = local_resource(tmp_path, monkeypatch, ("one",))
    index = mesh_index.add_mesh_index("道路", [resource])
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    assert not mesh_index._pending
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_mesh_index.py -k kumoy -q`
Expected: FAIL（`AttributeError: module 'ksj.mesh_index' has no attribute 'kumoy_upload'`）

- [ ] **Step 3: 実装する**

`ksj/mesh_index.py`:
- `from . import catalog, encoding_check, local_storage, temporary_files, zip_scanner` に `kumoy_upload` を加える。
- `load_mesh` の `mode = local_storage.loading_mode()` の直後に追加する。

```python
    if mode == "kumoy" and not kumoy_upload.ready():
        return
```

- `_finish_loading` の `if not selected or not _is_current(task, layer_id, url): return False` の直後に追加する。

```python
    if mode == "kumoy":
        # 一時ディレクトリの削除はアップロード処理に委ねる。
        kumoy_upload.upload_layers(
            [(provider, uri, name) for provider, path, name, uri in selected], workspace
        )
        return True
```

- [ ] **Step 4: テストと lint を通す**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_mesh_index.py -q`
Expected: PASS

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format .`
Expected: エラーなし

- [ ] **Step 5: コミット**

```bash
git add ksj/mesh_index.py tests/test_mesh_index.py
git commit -q -F - <<'EOF'
feat: メッシュ索引からの追加でも kumoy へアップロードする

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

---

### Task 7: README・画像・全体検証・実機確認

**Files:**
- Modify: `README.md`（「追加方法・保存先と再利用」「Python・バッチ処理で利用する」「構成」）
- Replace: `imgs/loading-settings.png`、`imgs/browser-loading-mode.png`（実機で取得）

- [ ] **Step 1: README を更新する**

「追加方法・保存先と再利用」の冒頭「次のどちらかを選びます」を「次のいずれかを選びます」にし、「一時レイヤーとして追加」の箇条書きの後に追加する。

```
- **kumoy にアップロードして追加**: 必要なファイルを一時フォルダへ取得し、[kumoy](https://www.kumoy.io/)（クラウド GIS）へアップロードします。完了後に kumoy のレイヤーを地図へ追加し、一時フォルダを削除するため、ローカルにファイルを残しません。
```

画像 2 枚の直後に小見出しを追加する。

```
#### kumoy にアップロードする

[kumoy](https://www.kumoy.io/) は地図データをクラウドで共有・公開できるサービスです。この追加方法には kumoy の QGIS プラグイン（QGIS 3.44 以上）が必要です。未インストールの場合は、設定画面で選んだときにその場でインストールを案内します。無効になっている場合は有効化を案内します。アップロードの前に、kumoy ブラウザパネルの Kumoy 項目からログインしてください。

ファイルをダブルクリックすると、必要なファイルを一時フォルダへ取得します。Shapefile は文字コードの確認画面が開き、判定した文字コードを初期値に、先頭の地物の属性をプレビューしながら UTF-8 / Shift_JIS / EUC-JP を選べます。GeoJSON・GML・GeoPackage は UTF-8 固定のため確認しません。続いて kumoy のアップロード画面が開き、送り先のプロジェクトとレイヤー名を選びます。ジオメトリの種類や件数などの制約は kumoy の画面で確認できます。

アップロードが完了すると kumoy のレイヤーを地図へ追加し、一時フォルダを削除します。kumoy ブラウザで選択中のプロジェクトと違うプロジェクトへ送った場合は地図へ追加できないため、kumoy ブラウザでプロジェクトを切り替えてから追加してください。メッシュ索引からの追加も同じ流れです。
```

「Python・バッチ処理で利用する」の末尾に追加する。

````
kumoy へは、`ksj:download_resource` → `ksj:load_layer` → `kumoy:uploadvector`（ラスタは `kumoy:uploadraster`）をモデルビルダーや Python で連結します。`ksj:load_layer` の `ENCODING` で文字コードを確かめ、`kumoy:uploadvector` の `INPUT` に `OUTPUT` を、`PROJECT_ID` に kumoy のプロジェクト ID を渡します。

```python
layer = processing.run("ksj:load_layer", {"SOURCE": source, "PROVIDER": "ogr"})["OUTPUT"]
processing.run("kumoy:uploadvector", {"INPUT": layer, "PROJECT_ID": project_id})
```
````

「構成」の表に次の行を加える（`ksj/encoding_check.py` の行の後）。

```
| `ksj/kumoy_upload.py`          | kumoy プラグインの確認・インストール支援・アップロード           |
```

- [ ] **Step 2: 全体検証**

Run: `bash scripts/test-docker.sh`
Expected: 全テスト PASS

Run: `QGIS_TEST_IMAGE=qgis/qgis:4.0-trixie bash scripts/test-docker.sh && QGIS_TEST_IMAGE=qgis/qgis:4.2-trixie bash scripts/test-docker.sh`
Expected: 全テスト PASS

Run: `uv run --no-sync ruff check . && uv run --no-sync ruff format --check .`
Expected: エラーなし

Run: README「Qt6 互換チェック」の docker コマンド、続けて `grep -i "ksj/kumoy_upload\|ksj/encoding_check\|ksj/local_storage\|ksj/catalog_browser" pyqt6_checker.log || echo "指摘なし"`
Expected: 「指摘なし」

- [ ] **Step 3: コミット**

```bash
git add README.md
git commit -q -F - <<'EOF'
docs: kumoy にアップロードして追加する方法を記載

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

- [ ] **Step 4: 実機確認（利用者に文章で依頼し、結果を待つ）**

QGIS 3.44（`/Applications/QGIS-LTR.app`）に kumoy プラグインを入れた状態と入れていない状態で確認する。確認項目を箇条書きで提示し、結果は文章で受け取る。

1. kumoy 未インストールで設定画面の kumoy を選ぶと確認が出て、了承後に QGIS のインストール画面が進み、完了後に設定が kumoy になること。
2. 未ログインでファイルをダブルクリックすると「kumoy ブラウザパネルの Kumoy 項目からログインしてください。」が出て取得しないこと。
3. `.cpg` の無い cp932 の Shapefile（例: 旧形式の行政区域）で文字コード確認画面が Shift_JIS 初期値・正しいプレビューで開き、アップロード後に kumoy 側の属性が文字化けしていないこと。
4. GeoJSON 1 件とラスタ 1 件（ある場合）が確認画面なしでアップロードされ、kumoy のレイヤーが地図に追加されること。
5. メッシュ索引からの kumoy アップロード。
6. 完了後に一時フォルダ（`ksj-layer-*`）が残っていないこと。
7. 設定画面と先頭項目の表示。画像 `imgs/loading-settings.png` と `imgs/browser-loading-mode.png` を新しい文言で取得し直す（過去に使った QGIS Python の `grab()` による取得手順を使う）。

- [ ] **Step 5: 画像をコミットし PR を作る**

```bash
git add imgs/loading-settings.png imgs/browser-loading-mode.png
git commit -q -F - <<'EOF'
docs: 設定画面とブラウザ先頭項目の画像を kumoy 追加後の表示に更新

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01BYS3eSHL8hoWQqnddzMhgc
EOF
```

作業ブランチは PR 2 のブランチから派生させる（`feat/kumoy-destination`）。PR 本文には影響範囲、テスト結果、実機確認の結果、設計書へのリンク、kumoy 側への依存事項（設計書の表）を書く。
