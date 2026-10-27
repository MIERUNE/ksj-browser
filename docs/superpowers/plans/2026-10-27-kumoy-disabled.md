# kumoy 連携の利用者向け無効化 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 追加方法「クラウド（kumoy）にアップロードして追加」を、コードとテストを残したまま 1 つのフラグで利用者から隠す。

**Architecture:** `ksj/kumoy_upload.py` に `ENABLED = False` を置き、`ksj/local_storage.py` の `available_modes()` が利用者の選べる追加方法をこのフラグで絞る。`loading_mode()` と設定画面 `LoadingSettingsDialog` だけがこれを参照し、`layer_loading.py`・`mesh_index.py`・`catalog_browser.py` の `mode == "kumoy"` 分岐は到達不能になる。既存の kumoy テストはフィクスチャ `kumoy_enabled` でフラグを真にして動かし続ける。

**Tech Stack:** Python 3.9+、QGIS 3.44〜4.x（PyQt5/PyQt6）、pytest + pytest-qgis、Ruff

**Spec:** `docs/superpowers/specs/2026-10-27-kumoy-disabled-design.md`

## Global Constraints

- 対応バージョンは QGIS 3.44 以上 4.x まで。`qgisMinimumVersion=3.44` は変えない。
- Python 3.9 で動く構文に限る。
- パッケージ内は相対インポート（`from . import kumoy_upload`）。
- コメント・docstring・ドキュメント・コミットメッセージは日本語。コミットは Conventional Commits（`feat:` `fix:` `docs:` `test:` `chore:`）。
- テストと Ruff は `.venv` のバイナリで実行する。`uv run` は `uv.lock` を書き換えるので使わない。
  - テスト: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest <対象> -q`
  - Lint: `.venv/bin/ruff check . && .venv/bin/ruff format --check .`（整形は `.venv/bin/ruff format <ファイル>`）
- `ksj/layer_loading.py`・`ksj/mesh_index.py`・`ksj/catalog_browser.py`・`ksj/encoding_check.py`・`tests/test_kumoy_upload.py`・`tests/test_encoding_check.py` は変更しない。
- 作業ブランチは `chore/disable-kumoy`（設計書のコミット 07874d7 を含む）。worktree は作らない。
- コミットの末尾に次を付ける。

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01D1ZRC6pKc5RXjUiQCPpekn
```

---

## ファイル構成

| ファイル | 役割 | 作業 |
| --- | --- | --- |
| `ksj/kumoy_upload.py` | kumoy 連携本体 | 定数 `ENABLED = False` を追加（Task 1） |
| `ksj/local_storage.py` | 追加方法の設定と設定画面 | `available_modes()` 追加、`loading_mode()` の判定変更（Task 1）、設定画面の kumoy パネルをフラグで条件化、`accept()` を選択 ID 基準に（Task 2） |
| `tests/conftest.py` | 共有フィクスチャ | `kumoy_enabled` を追加（Task 1） |
| `tests/test_lazy_loading.py` | ブラウザ・設定画面・読み込みのテスト | 既存 5 件に `kumoy_enabled` を付与、新規 2 件（Task 1・2） |
| `tests/test_mesh_index.py` | メッシュ索引のテスト | 既存 2 件に `kumoy_enabled` を付与（Task 1） |
| `README.md` | 利用者向け説明 | kumoy の記述を外す（Task 3） |
| `metadata.txt` | プラグインのメタデータ | about から kumoy を外す（Task 3） |
| `AGENTS.md` | エージェント向け案内 | Recent Changes に無効化の 1 行（Task 3） |
| `docs/superpowers/specs/2026-10-24-kumoy-destination-design.md` | 旧設計書 | 冒頭に無効化の注記（Task 3） |
| `scripts/capture_readme_images.py` | README 画像の生成 | `loading-settings` の撮影を追加（Task 4） |
| `imgs/loading-settings.png` | 設定画面の画像 | 撮り直し（Task 4） |

---

### Task 1: フラグと選べる追加方法

`kumoy_upload.ENABLED` を足し、`loading_mode()` が保存値 `kumoy` を `save` に戻すようにする。既存の kumoy テストはフィクスチャで動かし続ける。

**Files:**
- Modify: `ksj/kumoy_upload.py:25`（`KUMOY_URL` の直前）
- Modify: `ksj/local_storage.py:73-76`（`loading_mode`）
- Modify: `tests/conftest.py:15`（import）、`tests/conftest.py:66-77` の直後（フィクスチャ）
- Modify: `tests/test_lazy_loading.py:598-600, 927-929, 960-962, 984-986, 997`（既存テストの引数）、`tests/test_lazy_loading.py` 末尾付近（新規テスト）
- Modify: `tests/test_mesh_index.py:1014-1022, 1044-1046`（既存テストの引数）

**Interfaces:**
- Produces: `ksj.kumoy_upload.ENABLED: bool`（既定 `False`）
- Produces: `ksj.local_storage.available_modes() -> tuple[str, ...]`（`MODES` のうち利用者が選べるもの。`kumoy` は `ENABLED` が真のときだけ含む）
- Produces: pytest フィクスチャ `kumoy_enabled`（`kumoy_upload.ENABLED` を `True` にする）
- Consumes: `ksj.local_storage.MODES == ("save", "temporary", "kumoy")`、`ksj.local_storage.MODE_KEY`、`tests.conftest.storage_settings`（`MODE_KEY` を試験用キーに退避する）

- [ ] **Step 1: 保存値 `kumoy` が `save` に戻るテストを書く**

`tests/test_lazy_loading.py` の `test_settings_modes_stay_exclusive_across_option_panels`（997 行目から始まる関数）の直後に追加する。`QgsSettings`・`local_storage`・`KsjRootItem` は既に import 済み。

```python
def test_stored_kumoy_mode_falls_back_to_save_while_disabled(
    qgis_app, storage_settings
):
    """無効化中は保存値が kumoy でも保存方式として扱い、ブラウザの行にも出さない。"""
    QgsSettings().setValue(local_storage.MODE_KEY, "kumoy")
    assert local_storage.loading_mode() == "save"
    root = KsjRootItem()
    item = root.createChildren()[0]
    assert "kumoy" not in item.name()
    assert "保存して追加" in item.name()
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lazy_loading.py::test_stored_kumoy_mode_falls_back_to_save_while_disabled -q`
Expected: FAIL（`assert 'kumoy' == 'save'`）

- [ ] **Step 3: フラグを足す**

`ksj/kumoy_upload.py` の `KUMOY_URL = "https://www.kumoy.io/"` の直前に挿入する。

```python
# 利用者向けには無効化中。True にすると設定画面に選択肢が戻り、保存値 "kumoy" も有効になる。
ENABLED = False
```

- [ ] **Step 4: `available_modes()` を足し、`loading_mode()` の判定を変える**

`ksj/local_storage.py` の `loading_mode` を次に置き換える（`MODES` の定義と `uses_temporary_workspace` は変えない）。

変更前:

```python
def loading_mode() -> str:
    """既存利用者は保存方式を引き継ぐ。設定は追加操作のたびに参照する。"""
    value = QgsSettings().value(MODE_KEY, "save", type=str)
    return value if value in MODES else "save"
```

変更後:

```python
def available_modes() -> tuple[str, ...]:
    """利用者が選べる追加方法。kumoy は無効化中で、フラグが真のときだけ含める。"""
    return tuple(mode for mode in MODES if mode != "kumoy" or kumoy_upload.ENABLED)


def loading_mode() -> str:
    """既存利用者は保存方式を引き継ぐ。設定は追加操作のたびに参照する。"""
    value = QgsSettings().value(MODE_KEY, "save", type=str)
    return value if value in available_modes() else "save"
```

- [ ] **Step 5: 新規テストが通ることを確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lazy_loading.py::test_stored_kumoy_mode_falls_back_to_save_while_disabled -q`
Expected: PASS

- [ ] **Step 6: 既存の kumoy テストが壊れたことを確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lazy_loading.py tests/test_mesh_index.py -q -k kumoy`
Expected: FAIL が複数（`loading_mode()` が `kumoy` を返さなくなったため）

- [ ] **Step 7: フィクスチャ `kumoy_enabled` を足す**

`tests/conftest.py` の import を変える。

変更前:

```python
from ksj import catalog, local_storage
```

変更後:

```python
from ksj import catalog, kumoy_upload, local_storage
```

`storage_settings` フィクスチャ（`yield` の後の 2 行の `QgsSettings().remove(...)` で終わる）の直後に追加する。

```python
@pytest.fixture
def kumoy_enabled(monkeypatch):
    """利用者向けに無効化中の kumoy 連携を、このテストの間だけ有効にする。"""
    monkeypatch.setattr(kumoy_upload, "ENABLED", True)
```

- [ ] **Step 8: 既存テストにフィクスチャを付ける**

`tests/test_lazy_loading.py` の 5 件。引数リストの末尾に `kumoy_enabled` を足す。本文は変えない。

```python
def test_browser_displays_current_preference_and_updates_after_dialog(
    qgis_app, storage_settings, monkeypatch, kumoy_enabled
):
```

```python
def test_settings_dialog_keeps_open_until_kumoy_is_available(
    storage_settings, monkeypatch, kumoy_enabled
):
```

```python
def test_kumoy_mode_hands_fetched_files_to_upload_and_keeps_nothing(
    qgis_app,
    qgis_new_project,
    storage_settings,
    http_data,
    temp_root,
    monkeypatch,
    kumoy_enabled,
):
```

```python
def test_kumoy_mode_does_not_fetch_without_plugin_or_login(
    qgis_app, storage_settings, http_data, monkeypatch, kumoy_enabled
):
```

```python
def test_settings_modes_stay_exclusive_across_option_panels(
    storage_settings, kumoy_enabled
):
```

`tests/test_mesh_index.py` の 2 件。

```python
def test_mesh_kumoy_mode_hands_selected_layers_to_upload(
    qgis_app,
    qgis_new_project,
    tmp_path,
    monkeypatch,
    storage_settings,
    temp_root,
    layer_choices,
    kumoy_enabled,
):
```

```python
def test_mesh_kumoy_mode_stops_before_fetching_when_not_ready(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, storage_settings, kumoy_enabled
):
```

- [ ] **Step 9: 対象ファイルのテストが全部通ることを確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lazy_loading.py tests/test_mesh_index.py tests/test_kumoy_upload.py tests/test_local_storage.py -q`
Expected: 全件 PASS

- [ ] **Step 10: Lint と整形**

Run: `.venv/bin/ruff format ksj/local_storage.py ksj/kumoy_upload.py tests/conftest.py tests/test_lazy_loading.py tests/test_mesh_index.py && .venv/bin/ruff check .`
Expected: エラーなし（整形で行の折り返しが変わった場合はそのまま採用する）

- [ ] **Step 11: コミット**

```bash
git add ksj/kumoy_upload.py ksj/local_storage.py tests/conftest.py tests/test_lazy_loading.py tests/test_mesh_index.py
git commit -m "feat: kumoy 連携をフラグで利用者向けに無効化し、保存値 kumoy を save に戻す"
```

---

### Task 2: 設定画面から kumoy の選択肢を隠す

フラグが偽なら kumoy のパネルを作らず、`accept()` は選択 ID から追加方法を求めて `self.kumoy` の有無に依存しないようにする。

**Files:**
- Modify: `ksj/local_storage.py:145-156`（kumoy パネルの生成）、`ksj/local_storage.py:180-194`（`accept`）
- Modify: `tests/test_lazy_loading.py`（Task 1 で足した `test_stored_kumoy_mode_falls_back_to_save_while_disabled` の直後に新規テスト）

**Interfaces:**
- Consumes: `ksj.kumoy_upload.ENABLED`、`ksj.local_storage.MODES`、`LoadingSettingsDialog.mode_group: QButtonGroup`（ボタン ID は `MODES.index(mode)`）
- Produces: `LoadingSettingsDialog.kumoy`（フラグが偽なら `None`、真なら `QRadioButton`）

- [ ] **Step 1: 無効化中は kumoy の選択肢が無いテストを書く**

`tests/test_lazy_loading.py` の `test_stored_kumoy_mode_falls_back_to_save_while_disabled` の直後に追加する。`QLabel`・`QRadioButton` は既に import 済み。

```python
def test_settings_dialog_hides_kumoy_while_disabled(storage_settings):
    """無効化中は選択肢もリンクも出さず、残り 2 方式はそのまま選べる。"""
    QgsSettings().setValue(local_storage.MODE_KEY, "save")
    dialog = local_storage.LoadingSettingsDialog()
    try:
        assert dialog.kumoy is None
        assert not [
            button
            for button in dialog.findChildren(QRadioButton)
            if "kumoy" in button.text()
        ]
        assert not [
            label
            for label in dialog.findChildren(QLabel)
            if "https://www.kumoy.io/" in label.text()
        ]
        dialog.temporary.setChecked(True)
        dialog.accept()
    finally:
        dialog.deleteLater()
    assert local_storage.loading_mode() == "temporary"
```

- [ ] **Step 2: 失敗を確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lazy_loading.py::test_settings_dialog_hides_kumoy_while_disabled -q`
Expected: FAIL（`assert dialog.kumoy is None` で `QRadioButton` が入っている）

- [ ] **Step 3: kumoy パネルをフラグで条件化する**

`ksj/local_storage.py` の `LoadingSettingsDialog.__init__` で、`self.kumoy = QRadioButton(...)` から `option("kumoy", ...)` の呼び出しまでを次に置き換える。

変更前:

```python
        self.kumoy = QRadioButton("クラウド（kumoy）にアップロードして追加")
        about = QLabel(f'<a href="{kumoy_upload.KUMOY_URL}">kumoy について</a>')
        about.setOpenExternalLinks(True)
        about.setToolTip(kumoy_upload.KUMOY_URL)
        option(
            "kumoy",
            self.kumoy,
            "取得したファイルを kumoy に送り、クラウド上のレイヤーを地図に追加します。"
            "送信後に一時ファイルを削除します。"
            "送信前に Shapefile の文字コードと、未定義の座標系を確認します。",
            about,
        )
```

変更後:

```python
        # kumoy は利用者向けに無効化中。フラグが真のときだけ選択肢を出す。
        self.kumoy = None
        if kumoy_upload.ENABLED:
            self.kumoy = QRadioButton("クラウド（kumoy）にアップロードして追加")
            about = QLabel(f'<a href="{kumoy_upload.KUMOY_URL}">kumoy について</a>')
            about.setOpenExternalLinks(True)
            about.setToolTip(kumoy_upload.KUMOY_URL)
            option(
                "kumoy",
                self.kumoy,
                "取得したファイルを kumoy に送り、クラウド上のレイヤーを地図に追加します。"
                "送信後に一時ファイルを削除します。"
                "送信前に Shapefile の文字コードと、未定義の座標系を確認します。",
                about,
            )
```

- [ ] **Step 4: `accept()` を選択 ID 基準にする**

変更前:

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
        QgsSettings().setValue(MODE_KEY, MODES[self.mode_group.checkedId()])
        loading_settings_signals.changed.emit()
        super().accept()
```

変更後:

```python
    def accept(self):
        mode = MODES[self.mode_group.checkedId()]
        if mode == "save":
            if not self.directory.text().strip():
                QMessageBox.warning(
                    self, "保存先が未設定です", "保存先フォルダを選択してください。"
                )
                return
            if _remember_directory(self.directory.text(), self) is None:
                return
        elif mode == "kumoy" and not kumoy_upload.ensure_available(self):
            # プラグインが整わなければ閉じず、設定も変えない。
            return
        QgsSettings().setValue(MODE_KEY, mode)
        loading_settings_signals.changed.emit()
        super().accept()
```

- [ ] **Step 5: 新規テストと設定画面の既存テストが通ることを確認する**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lazy_loading.py tests/test_local_storage.py -q`
Expected: 全件 PASS（`kumoy_enabled` を付けたテストでは従来どおり `dialog.kumoy` が使える）

- [ ] **Step 6: Lint と整形**

Run: `.venv/bin/ruff format ksj/local_storage.py tests/test_lazy_loading.py && .venv/bin/ruff check .`
Expected: エラーなし

- [ ] **Step 7: コミット**

```bash
git add ksj/local_storage.py tests/test_lazy_loading.py
git commit -m "feat: 無効化中は設定画面に kumoy の選択肢を出さない"
```

---

### Task 3: 利用者向けの説明から kumoy を外す

README・metadata.txt から利用者向けの記述を外し、AGENTS.md と旧設計書に無効化の注記を残す。

**Files:**
- Modify: `README.md:52, 54, 72-79, 97, 277`
- Modify: `metadata.txt:16`
- Modify: `AGENTS.md`（末尾の「Recent Changes」）
- Modify: `docs/superpowers/specs/2026-10-24-kumoy-destination-design.md:1-2`

**Interfaces:**
- Consumes: なし（文書のみ）
- Produces: なし

- [ ] **Step 1: README の選択肢の箇条書きから kumoy を外す**

次の 1 行を削除する（前後の「フォルダに保存して追加」「一時レイヤーとして追加」の行は残す）。

```markdown
- **クラウド（kumoy）にアップロードして追加**: 取得したファイルを [kumoy](https://www.kumoy.io/) に送り、クラウド上のレイヤーを地図に追加します。
```

- [ ] **Step 2: README の画像の代替テキストを変える**

変更前:

```markdown
![保存・一時レイヤー・kumoy を切り替える設定画面](imgs/loading-settings.png)
```

変更後:

```markdown
![保存と一時レイヤーを切り替える設定画面](imgs/loading-settings.png)
```

- [ ] **Step 3: README の kumoy の節を削除する**

見出し「#### クラウド（kumoy）にアップロードして追加」から、その後の 3 段落と空行までを削除する。削除後は「#### 一時レイヤーとして追加」の節の最終段落（「**プロジェクト保存だけでは一時データは残りません。**」で始まる）の後に空行 1 つを挟んで「### 地図のメッシュをクリックして追加する」が続く。削除する範囲は次のとおり。

```markdown
#### クラウド（kumoy）にアップロードして追加

[kumoy](https://www.kumoy.io/) は地図データをクラウドで共有・公開できるサービスです。この追加方法には kumoy の QGIS プラグイン（QGIS 3.44 以上）が必要です。未インストールの場合は設定画面でインストールを、無効の場合は有効化を案内します。アップロード前に、kumoy ブラウザパネルの Kumoy 項目からログインしてください。

ファイルをダブルクリックすると、必要なファイルを一時フォルダへ取得し、次の確認を経て kumoy へアップロードします。Shapefile は文字コードの確認画面が開き、自動判定を初期値に、先頭 5 地物の文字列属性を見ながら UTF-8 / Shift_JIS / EUC-JP を選べます。GeoJSON・GML・GeoPackage は UTF-8 固定のため確認しません。座標系が未定義のデータは、配布元の説明を確認して元データの座標系を選びます。座標値や保存済みファイルは変更せず、アップロードするレイヤーに設定します。キャンセルしたレイヤーは送りません。続いて kumoy のアップロード画面で送り先のプロジェクトとレイヤー名を選びます。ジオメトリや件数などの制約は kumoy の画面で確認できます。

完了後は kumoy のレイヤーを地図へ追加し、一時フォルダを削除するため、ローカルにファイルを残しません。保存済みデータを再利用した場合、その保存データは保持します。kumoy ブラウザで選択中と異なるプロジェクトへ送った場合は、プロジェクトを切り替えてから追加してください。メッシュ索引からの追加も同じ流れです。

```

- [ ] **Step 4: README のメッシュ手順 5 から kumoy を外す**

変更前（行末のみ抜粋）:

```markdown
「一時レイヤーとして追加」と「クラウド（kumoy）にアップロードして追加」では毎回すべてのレイヤーを候補に出します。
```

変更後:

```markdown
「一時レイヤーとして追加」では毎回すべてのレイヤーを候補に出します。
```

- [ ] **Step 5: README の構成表に無効化を注記する**

変更前:

```markdown
| `ksj/kumoy_upload.py`              | kumoy プラグインの確認・インストール支援・アップロード       |
```

変更後（列幅は揃えなくてよい。Markdown の表として読めればよい）:

```markdown
| `ksj/kumoy_upload.py`              | kumoy プラグインの確認・インストール支援・アップロード（無効化中。`ENABLED` で切り替え） |
```

`ksj/layer_loading.py`・`ksj/encoding_check.py` の行は変えない。

- [ ] **Step 6: metadata.txt の about から kumoy を外す**

`about=` の行の中の次の部分を置き換える。

変更前:

```
フォルダ保存・一時レイヤー・kumoy へのアップロードの追加方法に対応します。
```

変更後:

```
フォルダ保存・一時レイヤーの追加方法に対応します。
```

- [ ] **Step 7: AGENTS.md の Recent Changes に 1 行足す**

末尾の箇条書きの最後に追加する。

```markdown
- kumoy 連携（`ksj/kumoy_upload.py`）は `ENABLED = False` で利用者向けに無効化中。復活時はフラグを真にし、README の説明と `imgs/loading-settings.png` を戻す（`docs/superpowers/specs/2026-10-27-kumoy-disabled-design.md`）。
```

- [ ] **Step 8: 旧設計書の冒頭に注記を足す**

`docs/superpowers/specs/2026-10-24-kumoy-destination-design.md` の 1 行目の見出しの直後に、空行を挟んで追加する。

```markdown
# 国土数値情報を kumoy にアップロードする追加方法

> 2026-10-27: 利用者向けに無効化（`docs/superpowers/specs/2026-10-27-kumoy-disabled-design.md`）。本文は当時のまま。
```

- [ ] **Step 9: 残った kumoy の記述を確認する**

Run: `git grep -n -i kumoy -- README.md metadata.txt`
Expected: README の構成表の 2 行（`ksj/layer_loading.py` と `ksj/kumoy_upload.py`）だけ。metadata.txt は 0 件。

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_readme_assets.py tests/test_metadata.py -q`
Expected: 全件 PASS

- [ ] **Step 10: コミット**

```bash
git add README.md metadata.txt AGENTS.md docs/superpowers/specs/2026-10-24-kumoy-destination-design.md
git commit -m "docs: 利用者向けの説明から kumoy を外し、無効化中の注記を残す"
```

---

### Task 4: 設定画面の画像を撮り直す

`scripts/capture_readme_images.py` に設定画面の撮影を加え、kumoy の選択肢が無い `imgs/loading-settings.png` を生成する。macOS のホスト QGIS.app で実行する。

**Files:**
- Modify: `scripts/capture_readme_images.py:1-12`（docstring）、`scripts/capture_readme_images.py:221`（`capture_mesh_resource_dialog` の直前に関数追加）、`scripts/capture_readme_images.py:259-264`（`CAPTURES`）
- Replace: `imgs/loading-settings.png`

**Interfaces:**
- Consumes: `ksj.local_storage.LoadingSettingsDialog`（Task 2 の結果。`__init__` が `resize(600, sizeHint().height())` を自分で行う）、スクリプト内の `settle(app)`・`save_1x(pixmap, path)`、`main()` が差し替える `local_storage.loading_mode`（`"temporary"`）と `local_storage.download_directory`（`""`）
- Produces: `CAPTURES["loading-settings"]`

- [ ] **Step 1: docstring の枚数を直す**

変更前:

```python
    .venv/bin/python scripts/capture_readme_images.py                     # 4 枚すべて
```

変更後:

```python
    .venv/bin/python scripts/capture_readme_images.py                     # 5 枚すべて
```

- [ ] **Step 2: 撮影関数を足す**

`def capture_mesh_resource_dialog(app, path):` の直前に追加する。ダイアログは `__init__` で幅 600 に整えるので `resize` は呼ばない。`main()` が `loading_mode` を `"temporary"` に差し替えているため「一時レイヤーとして追加」が選ばれた状態で写る。

```python
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
```

- [ ] **Step 3: `CAPTURES` に登録する**

変更前:

```python
CAPTURES = {
    "browser-panel-light": capture_browser_panel,
    "browser-loading-mode": capture_loading_mode,
    "browser-loading-indicator": capture_loading_indicator,
    "mesh-resource-dialog": capture_mesh_resource_dialog,
}
```

変更後:

```python
CAPTURES = {
    "browser-panel-light": capture_browser_panel,
    "browser-loading-mode": capture_loading_mode,
    "browser-loading-indicator": capture_loading_indicator,
    "loading-settings": capture_loading_settings,
    "mesh-resource-dialog": capture_mesh_resource_dialog,
}
```

- [ ] **Step 4: 画像を生成する**

Run: `source setup_qgis_env.sh && .venv/bin/python scripts/capture_readme_images.py --only loading-settings`
Expected: `saved /Users/yamakei/Documents/GitHub/ksj-provider/imgs/loading-settings.png 600x<高さ>` と表示され、ウィンドウが 0.5 秒ほど画面に出る。Aqua に固定できなかった旨が出た場合は、ダーク表示の画像になっていないか次の Step で確かめる。

- [ ] **Step 5: 画像を目で確認する**

`imgs/loading-settings.png` を Read ツールで開き、次を確かめる。

- 選択肢が「フォルダに保存して追加」「一時レイヤーとして追加」の 2 つだけで、kumoy の枠と「kumoy について」のリンクが無い。
- 「一時レイヤーとして追加」が選ばれ、保存先の欄はプレースホルダ「保存先フォルダ」で無効表示。
- 背景が明るい（ライト表示）。

Run: `git diff --stat -- imgs/loading-settings.png`
Expected: バイナリ差分として 1 ファイルが変更されている。

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_readme_assets.py -q`
Expected: PASS

- [ ] **Step 6: Lint**

Run: `.venv/bin/ruff format scripts/capture_readme_images.py && .venv/bin/ruff check .`
Expected: エラーなし

- [ ] **Step 7: コミット**

```bash
git add scripts/capture_readme_images.py imgs/loading-settings.png
git commit -m "docs: 設定画面の画像を kumoy の選択肢なしで撮り直し、生成スクリプトに加える"
```

---

### Task 5: 全体検証

設計書の「検証」節をすべて実行し、結果をまとめる。コードの変更はない。

**Files:**
- なし（検証のみ）

**Interfaces:**
- Consumes: Task 1〜4 の成果
- Produces: なし

- [ ] **Step 1: 全テスト**

Run: `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests -q`
Expected: 全件 PASS（skip は `tests/test_plugin_package.py` など既存の条件付きのみ）

- [ ] **Step 2: Lint と整形の確認**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: どちらもエラーなし

- [ ] **Step 3: 到達不能の確認**

Run: `git grep -n -i kumoy -- README.md metadata.txt`
Expected: README の構成表の 2 行だけ

Run: `git diff --stat main..HEAD -- ksj/layer_loading.py ksj/mesh_index.py ksj/catalog_browser.py ksj/encoding_check.py tests/test_kumoy_upload.py tests/test_encoding_check.py`
Expected: 出力なし（これらのファイルは変更していない）

- [ ] **Step 4: 作業状態の確認**

Run: `git status --short && git log --oneline main..HEAD`
Expected: 作業ツリーはクリーン。コミットは設計書・計画書・Task 1〜4 の 6 件。
