# kumoy 連携の利用者向け無効化 設計書

作成日: 2026-10-27

## 目的

追加方法「クラウド（kumoy）にアップロードして追加」は、利用者にとって十分に便利にならなかったため、利用者から使えないようにする。将来復活する可能性があるので、コードとテストは残し、1 つのフラグで選択肢を隠す。

## 背景

kumoy 連携は PR #32（`feat/kumoy-upload`）で入り、次の箇所に広がっている。

- `ksj/kumoy_upload.py`: プラグインの確認・導入支援・アップロード処理
- `ksj/local_storage.py`: 追加方法 `MODES` と設定画面 `LoadingSettingsDialog` の kumoy パネル
- `ksj/layer_loading.py`・`ksj/mesh_index.py`: `mode == "kumoy"` のときの `ready()` 確認とアップロードへの引き渡し
- `ksj/catalog_browser.py`: ブラウザ先頭の「追加方法」行の kumoy 表示
- `ksj/encoding_check.py`: アップロード前の文字コード確認ダイアログ（判定・適用は保存／一時レイヤーでも使う共有部分）
- `tests/test_kumoy_upload.py` ほか、`tests/test_lazy_loading.py`・`tests/test_mesh_index.py`・`tests/test_encoding_check.py` の kumoy を通るテスト
- `README.md`・`metadata.txt`・`imgs/loading-settings.png` の利用者向け説明

利用者が kumoy モードに入る入口は 2 つしかない。設定画面で選ぶことと、QgsSettings の `ksj/loading_mode` に保存された値を `loading_mode()` が返すことである。この 2 つをフラグで閉じれば、残りの分岐はすべて到達不能になる。

プラグインは未リリース（タグ・Release なし）で、保存値 `kumoy` を持つ環境は開発機に限られる。

## 方針

採用: **機能フラグで無効化する**。`kumoy_upload.ENABLED = False` を 1 つ置き、`local_storage` 側で「利用者が選べる追加方法」をこのフラグで絞る。kumoy 関連のコードは変更せず、既存テストはフィクスチャでフラグを真にして動かし続ける。

却下: 設定画面のパネルだけ消す案。保存値 `kumoy` が有効なまま残り、設定画面を開いたときにどのラジオも選ばれず、OK で `kumoy` を書き戻す不具合が出る。kumoy を選ぶテストも削除することになり、復活時に画面とテストを書き直す必要がある。

## 変更内容

### フラグ（`ksj/kumoy_upload.py`）

モジュール先頭の定数群に次を加える。

```python
# 利用者向けには無効化中。True にすると設定画面に選択肢が戻り、保存値 "kumoy" も有効になる。
ENABLED = False
```

他の関数・定数は変更しない。

### 選べる追加方法（`ksj/local_storage.py`）

- `MODES = ("save", "temporary", "kumoy")` は並び順とボタン ID の定義として残す。
- `available_modes()` を足す。`MODES` のうち、`kumoy` は `kumoy_upload.ENABLED` が真のときだけ含めたタプルを返す。
- `loading_mode()` の判定を `value in MODES` から `value in available_modes()` に変える。保存値が `kumoy` でフラグが偽なら `save` を返す。
- `uses_temporary_workspace()` は変更しない。

### 設定画面（`LoadingSettingsDialog`）

- `self.kumoy = None` を先に置き、`kumoy_upload.ENABLED` が真のときだけ、現在の kumoy パネル（ラジオ、説明、「kumoy について」リンク）を `option()` で作って `self.kumoy` に入れる。`option()` 自体は変更しない。
- `accept()` は `self.save.isChecked()` と `self.kumoy.isChecked()` を見る代わりに、`MODES[self.mode_group.checkedId()]` で選択中の追加方法を求める。`save` なら保存先の検証、`kumoy` なら `ensure_available()` の確認を行い、通れば `MODE_KEY` にその値を書く。`self.kumoy` の有無に依存しない。
- フラグが偽のとき、`loading_mode()` が `save` か `temporary` しか返さないので、開いた時点で必ずどちらかのラジオが選ばれている。

### 変更しないモジュール

`ksj/layer_loading.py`・`ksj/mesh_index.py`・`ksj/catalog_browser.py`・`ksj/encoding_check.py` は変更しない。`mode == "kumoy"` の分岐はフラグが偽の間は到達しないが、復活時にそのまま使う。

### 既存利用者への影響

保存値 `kumoy` の環境では、次の追加操作から `save` として扱う。保存先が未設定なら従来どおり設定画面が開く。レイヤーや保存済みファイルには影響しない。

## テスト

### フィクスチャ

`tests/conftest.py` に `kumoy_enabled(monkeypatch)` を足し、`kumoy_upload.ENABLED` を `True` にする。

### 既存テストの扱い

`loading_mode()` または設定画面の kumoy ラジオを通るテストに `kumoy_enabled` を付け、中身は変えない。

- `tests/test_lazy_loading.py`: `test_browser_displays_current_preference_and_updates_after_dialog`、`test_settings_dialog_keeps_open_until_kumoy_is_available`、`test_kumoy_mode_hands_fetched_files_to_upload_and_keeps_nothing`、`test_kumoy_mode_does_not_fetch_without_plugin_or_login`、`test_settings_modes_stay_exclusive_across_option_panels`
- `tests/test_mesh_index.py`: `test_mesh_kumoy_mode_hands_selected_layers_to_upload`、`test_mesh_kumoy_mode_stops_before_fetching_when_not_ready`

`tests/test_kumoy_upload.py` と `tests/test_encoding_check.py` は `upload_layers()`・`_finish()`・`finish_loading()`・`confirm_encoding()` を直接呼び、`loading_mode()` も設定画面も通らないため変更しない。

### 新規テスト（`tests/test_lazy_loading.py`、既存の設定画面テストの隣）

1. `test_settings_dialog_hides_kumoy_while_disabled`: 既定（フラグ偽）で `LoadingSettingsDialog` を作ると、`dialog.kumoy` が `None` で、ラジオボタンの文言に `kumoy` を含むものが無く、`QLabel` に `https://www.kumoy.io/` を含むものが無い。`temporary` を選んで OK を押すと `loading_mode()` が `temporary` になる。
2. `test_stored_kumoy_mode_falls_back_to_save_while_disabled`: `MODE_KEY` に `kumoy` を書いた状態で `loading_mode()` が `save` を返し、`KsjRootItem` の先頭の「追加方法」行の名前に `kumoy` を含まず「保存して追加」を含む。

## ドキュメントと画像

### `README.md`

- 「追加方法・保存先を設定する」の選択肢の箇条書きから「クラウド（kumoy）にアップロードして追加」を外す。
- 画像の代替テキストを「保存・一時レイヤー・kumoy を切り替える設定画面」から「保存と一時レイヤーを切り替える設定画面」に変える。
- 「#### クラウド（kumoy）にアップロードして追加」の節（見出しと 3 段落）を削除する。
- メッシュ手順 5 の末尾を「「一時レイヤーとして追加」では毎回すべてのレイヤーを候補に出します。」に変える。
- 構成表の `ksj/kumoy_upload.py` の行を「kumoy プラグインの確認・インストール支援・アップロード（無効化中。`ENABLED` で切り替え）」にする。`ksj/layer_loading.py`・`ksj/encoding_check.py` の行はコードの実態どおりなので変えない。

### `metadata.txt`

`about=` の「フォルダ保存・一時レイヤー・kumoy へのアップロードの追加方法に対応します」を「フォルダ保存・一時レイヤーの追加方法に対応します」に変える。

### `imgs/loading-settings.png`

`scripts/capture_readme_images.py` の `CAPTURES` に `loading-settings` を加え、生成した画像で置き換える。

- `capture_loading_settings(app, path)`: `local_storage.LoadingSettingsDialog()` を作り、`resize(600, sizeHint().height())`、`show()`、`settle(app)` の後に `save_1x(dialog.grab(), path)` し、`close()` する。
- `main()` は既に `loading_mode` を `temporary`、`download_directory` を空に差し替えているので、「一時レイヤーとして追加」が選ばれ、保存先は空欄のプレースホルダ表示になる。ブラウザの画像 `browser-loading-mode.png` と同じ状態である。
- 実行は `source setup_qgis_env.sh && .venv/bin/python scripts/capture_readme_images.py --only loading-settings`。

### `AGENTS.md`

「Recent Changes」に 1 行足す。「kumoy 連携（`ksj/kumoy_upload.py`）は `ENABLED = False` で利用者向けに無効化中。復活時はフラグを真にし、README の説明と `imgs/loading-settings.png` を戻す。」

### `docs/superpowers/specs/2026-10-24-kumoy-destination-design.md`

冒頭に「2026-10-27: 利用者向けに無効化（`docs/superpowers/specs/2026-10-27-kumoy-disabled-design.md`）」の 1 行を足す。本文は変えない。

## 復活手順

1. `kumoy_upload.ENABLED` を `True` にする。
2. 無効化中を前提にした `tests/test_lazy_loading.py` の 2 件（`test_stored_kumoy_mode_falls_back_to_save_while_disabled`、`test_settings_dialog_hides_kumoy_while_disabled`）を削除する。既存の kumoy テストに付けたフィクスチャ `kumoy_enabled` は残しても害はない。
3. README の削除した記述を本設計書の変更前の内容（コミット履歴）から戻し、`metadata.txt` の about に kumoy を戻す。
4. `scripts/capture_readme_images.py --only loading-settings` で画像を撮り直す。
5. `AGENTS.md` と 2026-10-24 の設計書の注記を外す。

## 範囲外

- `qgisMinimumVersion=3.44` は kumoy プラグインに合わせて上げた経緯があるが、戻すには API の確認と CI マトリクスの変更が要るため扱わない。
- kumoy 関連コードの削除・整理はしない。
- kumoy の分岐を持つモジュールのカバレッジは、フラグを真にした既存テストで維持する。

## 検証

- `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests -q` が通ること。
- `.venv/bin/ruff check .` と `.venv/bin/ruff format --check .` が通ること。
- `imgs/loading-settings.png` に kumoy の選択肢が写っていないこと。
- `git grep -i kumoy -- README.md metadata.txt` の結果が、構成表の 2 行（`ksj/layer_loading.py`・`ksj/kumoy_upload.py`）だけであること。
