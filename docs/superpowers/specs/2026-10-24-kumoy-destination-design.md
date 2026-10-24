# 国土数値情報を kumoy にアップロードする追加方法

## 目的

「国土数値情報の追加方法・保存先」に、[kumoy](https://www.kumoy.io/) へアップロードする 3 つ目の方式を加える。利用者がこのプラグインを通じて kumoy を知る機会を作り、kumoy の利用者増加も狙う。アップロードの前に Shapefile の文字コードを確認し、文字化けした属性を kumoy へ送らない。取得したファイルはアップロード後に削除し、ローカルに残さない。

あわせて、文字コードの自動判定を既存の追加方法にも適用し、メッシュ索引からの追加が追加方法の設定に従うようにする。

## 利用者が承認した決定

- データの取得経路は既存の「一時レイヤー」経路を流用する。`/vsizip//vsicurl/` は使わない。GDAL が多数の Range リクエストを出し、プレビューの再読み込みでも通信が生じ、取消・進捗・QGIS のプロキシ設定が効かず、「新規レイヤー参照に `/vsicurl/` を使わない」という既存方針（[配布データのローカル保存](2026-10-22-local-download-storage-design.md)）にも反するため。
- 文字コードの確認ダイアログ（プレビュー付きの選択）は kumoy アップロード時の Shapefile だけに出す。既存の「一時レイヤー」「フォルダに保存」とメッシュ索引経路、Processing の `ksj:load_layer`（自動判定）では、ダイアログなしで判定結果を適用する。
- GeoJSON・GML・GeoPackage は確認しない。仕様上 UTF-8 であり、GDAL ドライバが「文字列は UTF-8」と宣言するため QGIS は `setProviderEncoding()` を無視する。
- kumoy プラグイン側は変更しない。アップロードは kumoy の Processing アルゴリズム経由とし、kumoy の内部モジュールは import しない。
- アップロード完了後は kumoy のレイヤーを地図にも追加する。追加できなければ通知にとどめる。
- kumoy プラグインが未インストールなら、確認のうえ QGIS のプラグインインストーラでその場でインストールする。失敗時はプラグインマネージャを開く。
- このプラグインの最低 QGIS バージョンを kumoy と同じ 3.44 に引き上げる。
- メッシュ索引からの追加は、追加方法の設定（保存・一時レイヤー・kumoy）の 3 方式すべてに従う。
- Processing では `ksj:load_layer` に文字コードパラメータを追加し、kumoy へは `ksj:download_resource` → `ksj:load_layer` → `kumoy:uploadvector` の連結で対応する。専用アルゴリズムは後続の Issue とする。

## 方式の比較

- **kumoy の Processing ダイアログを流用（採用）**: 取得と文字コード確認までを本プラグインが担い、プロジェクト選択・レイヤー名・フィールド選択・制約チェックは `processing.execAlgorithmDialog("kumoy:uploadvector", {"INPUT": layer})` に委ねる。kumoy 自身のブラウザパネルと同じ経路であり、kumoy の更新に追従する。ダイアログの文言は本プラグインの統制外で、INPUT の候補に他のプロジェクトレイヤーも並ぶ。
- 本プラグイン独自の統合ダイアログ: 文字コード確認・組織とプロジェクト選択・レイヤー名を 1 画面にまとめ `processing.run("kumoy:uploadvector", {"PROJECT_ID": ...})` を呼ぶ。一覧 UI・進捗・エラー表示を自前で持つことになり、kumoy の UI と乖離するため不採用。
- kumoy の内部モジュールを直接利用: `get_token` や `DialogLogin` を import する。kumoy のリファクタで壊れるため不採用。

## 実測で確認済みの前提

QGIS 3.42.1（macOS）で確認した。

- Shapefile は `.cpg` があれば QGIS がそれを使い、無ければ UTF-8 で読む（macOS）。`QgsVectorLayer.setProviderEncoding("Shift_JIS")` は `.cpg` の有無にかかわらず上書きでき、cp932 の `.dbf` を正しく読めた。
- Processing のアルゴリズムダイアログは、`QgsProject` に登録されていないレイヤーを INPUT に事前指定しても受け付けない（値が空になる）。`QgsProject.instance().addMapLayer(layer, False)` でレイヤーツリーに出さずに登録すれば受け付ける。

## kumoy プラグインへの依存事項

本プラグインが依存する kumoy 側の事項は次に限る。変更があれば `ksj/kumoy_upload.py` の定数で追従する。

| 事項 | 値 |
| --- | --- |
| Processing プロバイダ ID | `kumoy` |
| アップロード | `kumoy:uploadvector`（`INPUT`、出力 `VECTOR_ID`）、`kumoy:uploadraster`（`INPUT`、出力 `RASTER_ID`） |
| 地図への追加 | `kumoy:addvectortomap`（`VECTOR_ID`）、`kumoy:addrastertomap`（`RASTER_ID`）。いずれも GUI スレッド専用で、kumoy ブラウザで選択中のプロジェクトに属する項目だけ追加できる |
| ログイン状態 | `QSettings` の `Kumoy/session_token` が空でないこと |
| 公式リポジトリのパッケージ名 | `kumoy_qgis_plugin`（`metadata.txt` の `name` は `Kumoy`） |
| 必要 QGIS | 3.44 以上 |
| 公式サイト | `https://www.kumoy.io/` |

アップロード時の制約（Point / LineString / Polygon のみ、EPSG:4326 へ再投影、マルチパート分解、文字列 255 文字、ラスタは GDAL プロバイダのみで COG 変換後 4 GB 以下）は kumoy のダイアログ内で検査・表示されるため、本プラグインでは扱わない。

## 動作

### 設定

- `local_storage.loading_mode()` の値に `"kumoy"` を加える。保存キーは既存の `ksj/loading_mode` のまま。
- 設定ダイアログのラジオは「フォルダに保存して追加」「一時レイヤーとして追加」「kumoy にアップロードして追加」の順。3 つ目のラジオと同じ行の右に、`QLabel` で `kumoy について` を `https://www.kumoy.io/` へのリンクとして置く（`setOpenExternalLinks(True)`）。説明文に「kumoy へは必要なファイルを一時フォルダへ取得してアップロードし、完了後に一時フォルダを削除します。Shapefile は文字コードを確認してから送ります。」を加える。
- OK で kumoy が選ばれているとき、`kumoy_upload.ensure_available(self)` を呼ぶ。False ならダイアログを閉じず、設定も変えない。
- ブラウザ先頭の項目は「追加方法: kumoy にアップロード（ローカルに保存しない）」と表示し、ツールチップに `https://www.kumoy.io/` を含める。

### 事前確認（`ksj/kumoy_upload.py`）

- `is_available()`: `QgsApplication.processingRegistry().providerById("kumoy")` が None でないこと。インストール先フォルダ名に依存しない。
- `is_logged_in()`: `QSettings().value("Kumoy/session_token", "")` が空でないこと。
- `ensure_available(parent) -> bool`:
  1. 利用可能なら True。
  2. `qgis.utils.updateAvailablePlugins()` で一覧を更新し、インストール済みで無効なら（`qgis.utils.available_plugins` のうち `qgis.utils.pluginMetadata(name, "name") == "Kumoy"` のもの）、「kumoy プラグインを有効化しますか」と確認し、`loadPlugin` と `startPlugin` を実行して `QgsSettings` の `PythonPlugins/<package>` を True にする。
  3. 未インストールなら「kumoy へのアップロードには kumoy プラグインが必要です。インストールしますか？」と確認する。文中の kumoy は公式サイトへのリンク。了承後、`pyplugin_installer.instance()` の `fetchAvailablePlugins(reloadMode=False)` を行い、`pyplugin_installer.installer_data.plugins.all()` に `kumoy_qgis_plugin` があれば `installPlugin("kumoy_qgis_plugin")` を呼ぶ（QGIS 標準の進行ダイアログが出る）。一覧に無い、または例外が出た場合は `showPluginManagerWhenReady()` でプラグインマネージャを開き、「Kumoy を検索してインストールしてください」と通知する。
  4. いずれの後も `is_available()` を再確認して返す。
- `ready(parent) -> bool`: `ensure_available()` が False なら False。`is_logged_in()` が False なら「kumoy ブラウザパネルの Kumoy 項目からログインしてください」と通知して False。追加操作の開始時に使う。

### ブラウザ経路（`ksj/layer_loading.py`）

- `start()`: 追加方法が kumoy なら `kumoy_upload.ready()` が False の時点で中止する。`LoadKey` の mode に `"kumoy"` が入るため、他方式の同じファイルと並行しても衝突しない。
- `prepare()`: 一時ディレクトリは mode が `"temporary"` または `"kumoy"` のときに作る。単体ファイル（ZIP でない配布）でも、保存先に取得済みがあれば通信せず再利用する。そのため `local_storage.saved_local_data(url, directory)`（完成済みなら保存パス、なければ None）を追加し、`remote_zip.saved_member()` と対にする。
- `_finish()`: mode が kumoy なら `kumoy_upload.upload_layers(result["layers"], workspace)` に委ね、一時ディレクトリの寿命も渡す（以後 `finally` で削除しない）。それ以外は従来どおりレイヤーを生成し、ベクタには `encoding_check.apply_detected_encoding(layer)` を適用してから追加する。

### メッシュ索引経路（`ksj/mesh_index.py`）

- `load_mesh()`: 追加方法を読む。`"save"` なら従来どおり保存先（未設定なら選択）へ取得する。`"temporary"` と `"kumoy"` なら一時ディレクトリを作り、kumoy の場合は先に `kumoy_upload.ready()` を確認する。
- `scan_resource(task, url, directory, temporary=None)`: `temporary` が指定されたとき、保存先に完成済みデータがあれば `saved_local_data()` で再利用し、なければ一時ディレクトリへ取得する。
- `finish_loading()` と `_finish_loading()` は mode と一時ディレクトリを受け取る。「追加済み」の除外と `ksj/loaded/<url>` の記録は `"save"` だけで行う。レイヤーへの `ksj/resource_url` の付与は `"save"` と `"temporary"` で行う（kumoy はローカルレイヤーを残さない）。一時ディレクトリはパスが毎回変わるため、同じ配布でも再度候補に出す。複数レイヤーの選択ダイアログは 3 方式で共通。
- `"temporary"` では追加したレイヤーに `temporary_files.release_when_closed(workspace, layers)` を適用し、全部閉じられた時点で一時ディレクトリを削除する。`"kumoy"` では選んだレイヤーを `kumoy_upload.upload_layers()` へ渡す。早期 return・例外時は一時ディレクトリを削除する。
- 索引レイヤーのアクションから起動する流れ、配布ファイルの選択、タスクの取消は変えない。

### kumoy アップロード処理（`kumoy_upload.upload_layers(layers, workspace, parent=None)`）

`layers` は `prepare()` と同じ `(provider, source, title)` の列。GUI スレッドで順に処理し、最後に一時ディレクトリを削除する（`workspace` が None なら削除しない）。

1. `provider` に応じて `QgsVectorLayer` / `QgsRasterLayer` を生成する。無効なら失敗一覧に加えて次へ。
2. ベクタで `source` が `.shp` を指すなら `encoding_check.confirm_encoding(layer, parent)` を呼ぶ。False（キャンセル）ならこのレイヤーを飛ばす。
3. `QgsProject.instance().addMapLayer(layer, False)` でレイヤーツリーに出さずに登録する。
4. ベクタは `processing.execAlgorithmDialog("kumoy:uploadvector", {"INPUT": layer})`、ラスタは `"kumoy:uploadraster"` を開く。戻り値の `VECTOR_ID` / `RASTER_ID` が無ければキャンセルとみなし、通知せず次のレイヤーへ進む。
5. `finally` で `removeMapLayer(layer.id())` する。
6. ID があれば `processing.runAndLoadResults("kumoy:addvectortomap", {"VECTOR_ID": id})`（ラスタは `addrastertomap` と `RASTER_ID`）で kumoy のレイヤーを地図へ追加し、「kumoy にアップロードしました: <レイヤー名>」と通知する。例外なら「アップロードは完了しました。kumoy ブラウザでプロジェクトを切り替えてから追加してください。」と通知する。
7. 全レイヤーの後、失敗一覧があれば「読み込めないレイヤー: ...」とまとめて警告する。

kumoy のダイアログ内で起きるエラー（未ログインの期限切れ、権限、制約違反）は kumoy が表示するため扱わない。

### 文字コード判定（`ksj/encoding_check.py`）

`detect_shapefile_encoding(shp_path) -> Detection`。`Detection` は `encoding`（`"UTF-8"` / `"Shift_JIS"` / None）、`reason`（利用者向けの根拠）、`confident`（属性バイト列から判定したか）を持つ `namedtuple`。ローカルの `.dbf` だけを読み、通信しない。

1. `.dbf` のヘッダ（レコード数、ヘッダ長、レコード長、フィールド定義）を直接解析し、先頭 20 レコードの文字列フィールド（型 `C`）の生バイト列を集める。
2. 非 ASCII バイトがあれば、厳密な UTF-8 復号に成功すれば `UTF-8`、失敗して cp932 復号に成功すれば `Shift_JIS`（いずれも `confident=True`）。どちらも失敗なら判定不能として 3 へ。
3. 補助判定を順に試す。`.cpg` の内容（`UTF-8`・`UTF8` → UTF-8、`CP932`・`SHIFT_JIS`・`SJIS`・`932` → Shift_JIS）、`.dbf` の 30 バイト目（0x13・0x7B → Shift_JIS）、パスの親フォルダ名（`utf-8`・`utf8` を含めば UTF-8、`shift_jis`・`sjis`・`cp932` を含めば Shift_JIS。国土数値情報が両版を `UTF-8` / `Shift_JIS` フォルダで同梱する配布に対応）。いずれも `confident=False`。
4. どれにも当てはまらなければ `encoding=None`、`reason` は「判定できませんでした」。非 ASCII バイトが無いときは表示に差が出ないため、補助判定があればそれを、なければ None を返す。

EUC-JP は国土数値情報に無いため自動判定しない。ダイアログの手動選択だけに残す。

`apply_detected_encoding(layer)`: `providerType() == "ogr"` で `source()` が `.shp` のレイヤーに対して判定し、`encoding` があれば `setProviderEncoding()` を呼ぶ。適用前と異なるときだけ `QgsMessageLog` に「文字コードを Shift_JIS と判定して適用: <ファイル名>」と記録する。None なら何もしない。

### 確認ダイアログ（`encoding_check.confirm_encoding(layer, parent) -> bool`）

- 文字列フィールドが無ければダイアログを出さず True を返す。
- タイトル「kumoy へアップロードする前に文字コードを確認」。内容はファイル名、判定根拠の 1 行、文字コードのコンボ（`UTF-8` / `Shift_JIS` / `EUC-JP`）、属性プレビューの表、ボタン「この内容でアップロード」「キャンセル」。
- コンボの初期値は `Detection.encoding`。None のときは `UTF-8` を選び、赤字で「文字コードを判定できませんでした。プレビューで確認してください。」と表示する。
- プレビューは `QgsFeatureRequest` で先頭 5 地物をジオメトリ無しで取得し、文字列フィールドだけを列にする。コンボ変更のたびに `layer.setProviderEncoding()` を呼んで表を更新する。ローカルファイルなので通信しない。
- OK 時点の文字コードがレイヤーに設定された状態で戻る。キャンセルは False。

### Processing（`ksj/processing_algorithms.py`）

- `ksj:load_layer` に `QgsProcessingParameterEnum("ENCODING", "文字コード", ["自動判定", "UTF-8", "Shift_JIS", "EUC-JP"], defaultValue=0)` を追加する。`CHOICES` に無いパラメータは標準ウィジェットで表示される。`ogr` のとき、「自動判定」は `apply_detected_encoding()`、それ以外は `setProviderEncoding()` を適用する。`gdal` では無視する。
- README に kumoy への連結手順を記載する。モデルビルダーまたは Python で `ksj:download_resource` → `ksj:load_layer` → `kumoy:uploadvector`（`INPUT` に `OUTPUT`、`PROJECT_ID` に kumoy のプロジェクト ID）をつなぐ。
- `ksj:download_resource` は従来どおり指定フォルダへ保存する。

### 最低バージョン

- `metadata.txt` の `qgisMinimumVersion` を `3.44` にする。
- `.github/workflows/test.yaml` の QGIS マトリクスから `3.40` を外し、`3.44` / `4.0-trixie` / `4.2-trixie` にする。
- README・AGENTS.md の対応バージョンを「3.44 以上 4.x まで」に改める。

### 共通化（既存コードの整理）

- `notify` と `log_message` を `ksj/mesh_index.py` から新モジュール `ksj/messages.py` へ移す。呼び出し側は `messages` を直接参照し、`mesh_index` では再エクスポートしない。
- `_cleanup` と `_release_when_closed` を `ksj/layer_loading.py` から新モジュール `ksj/temporary_files.py`（`cleanup`、`release_when_closed`、`workspace()`）へ移し、`layer_loading`・`mesh_index`・`kumoy_upload` が共用する。`workspace()` は `tempfile.TemporaryDirectory(prefix="ksj-layer-")` を返す。`mesh_index` が `layer_loading` を import する循環を避けるため。

### 文言と README

- README「追加方法・保存先と再利用」に「kumoy にアップロードして追加」の項を追加する。kumoy の紹介とリンク、kumoy プラグインが必要なこと（未インストール時はその場でインストールを案内）、ログインは kumoy ブラウザパネルから行うこと、Shapefile の文字コード確認、ローカルにファイルを残さないこと、完了後に kumoy レイヤーを地図へ追加することを記載する。
- 「地図のメッシュをクリックして追加する」と「Processingツールボックスから利用する」の、追加方法がメッシュ経路に適用されない旨の記述を改める。追加方法はブラウザのファイル項目とメッシュ索引に適用し、Processing の取得処理は指定フォルダへ保存する。
- 既存 2 方式で Shapefile の文字コードを自動判定して適用すること、判定結果はログで確認できることを記載する。
- `imgs/loading-settings.png` と `imgs/browser-loading-mode.png` は文言が変わるため差し替え対象とする。実機で取得する。

## 変更箇所

- 新規: `ksj/kumoy_upload.py`、`ksj/encoding_check.py`、`ksj/messages.py`、`ksj/temporary_files.py`
- 変更: `ksj/local_storage.py`（追加方法 `"kumoy"`、設定ダイアログ、`saved_local_data`）、`ksj/layer_loading.py`（開始時の確認、`prepare` の一時ディレクトリ条件と保存再利用、`_finish` の分岐と自動判定）、`ksj/mesh_index.py`（3 方式対応）、`ksj/catalog_browser.py`（表示文言）、`ksj/processing_algorithms.py`（`ENCODING`）、`metadata.txt`、`.github/workflows/test.yaml`、`README.md`、`AGENTS.md`

## 実装の分割

1 PR 1 トピックの方針に合わせ、依存順に 3 つの PR へ分ける。

1. 最低バージョン 3.44、`messages` と `temporary_files` への共通化、文字コード判定モジュールと既存 2 方式・`ksj:load_layer` への自動適用。
2. メッシュ索引経路の 3 方式対応（この時点では `"kumoy"` は未定義のため保存・一時レイヤーの 2 方式）。
3. 追加方法 `"kumoy"`、事前確認とインストール支援、確認ダイアログ、アップロード処理、README。

## 範囲外と後続

- kumoy プラグイン側の変更。
- `ksj:upload_to_kumoy` のような専用 Processing アルゴリズム。連結方式で様子を見て、要望があれば Issue で扱う。
- GeoJSON 等の壊れた UTF-8 を検出する安全策。実例を把握していないため入れない。
- kumoy へアップロード済みかどうかの重複判定。

## テスト（pytest-qgis）

- `tests/test_encoding_check.py`: cp932 / UTF-8 の `.dbf` をバイト列で生成し、`.cpg` の有無、LDID、親フォルダ名、非 ASCII 無し、判定不能の各分岐で `Detection` を確認する。`apply_detected_encoding` が `providerEncoding` を変え、ログを残すこと。`confirm_encoding` はコンボ変更でプレビューが変わること、OK で設定が残ること、キャンセルで False を返すこと、文字列フィールドが無ければダイアログを出さないこと。
- `tests/test_kumoy_upload.py`: テスト内で ID `kumoy` の偽 `QgsProcessingProvider`（`uploadvector` / `uploadraster` / `addvectortomap` / `addrastertomap` のスタブ）を登録し、`processing.execAlgorithmDialog` と `processing.runAndLoadResults` を差し替える。レイヤーがレイヤーツリーに出ずに登録されて INPUT に渡ること、ダイアログ後に登録解除されること、地図追加の成功・失敗の通知、キャンセル時にアップロードされないこと、一時ディレクトリが最後に削除されること、`.shp` だけで `confirm_encoding` が呼ばれることを確認する。`ensure_available` はインストーラと `qgis.utils` を差し替え、利用可能・無効・未インストール（一覧あり／なし）・例外の分岐を確認する。`ready` は未ログインで通知して False を返すこと。
- `tests/test_lazy_loading.py`: 追加方法 kumoy で `upload_layers` に委ねること（差し替え）、プラグイン不在・未ログインで `start()` が中止すること、既存 2 方式で cp932 の Shapefile（`.cpg` なし）を追加すると `providerEncoding` が `Shift_JIS` になること、単体ファイルの一時レイヤーが保存済みデータを再利用すること。
- `tests/test_mesh_index.py`: `"temporary"` で一時ディレクトリへ取得してレイヤーを閉じると削除されること、保存済みがあれば再利用すること、`"kumoy"` で `upload_layers` に委ねること、`"save"` の既存テストが変わらないこと。
- `tests/test_local_storage.py`: 追加方法 `"kumoy"` の保存と表示、設定ダイアログで kumoy を選び `ensure_available` が False のときダイアログが閉じず設定が変わらないこと。
- `tests/test_processing.py`: `ksj:load_layer` の `ENCODING` の自動判定と明示指定。
- `tests/test_metadata.py`: 最低バージョン 3.44。

## 検証

- Docker の全テスト（QGIS 3.44 / 4.0 / 4.2）、Ruff の check / format、pyqgis4-checker の dry run を通す。
- 実機で確認する。cp932 の Shapefile（`.cpg` なし）を kumoy にアップロードして属性が文字化けしないこと、GeoJSON とラスタの各 1 件、メッシュ索引からの kumoy アップロード、kumoy 未インストール状態からのインストール支援、未ログイン時の案内、「一時レイヤー」と「フォルダに保存」で cp932 の Shapefile が文字化けせずに追加されること、設定画面と先頭項目の表示。
