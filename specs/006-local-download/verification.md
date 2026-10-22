# 配布データのローカル保存 — 検証記録

## 対象

初回だけ選択した保存先を記憶し、未取得の配布原本をダウンロードしてから表示する。ブラウザ展開、ダブルクリック、ドラッグ用URI、メッシュ索引からの追加をローカル参照へ切り替えた。

- 実装: `ksj/local_storage.py`、`ksj/catalog_browser.py`、`ksj/browser.py`、`ksj/mesh_index.py`、`ksj/zip_scanner.py`
- 設計: [承認済みの動作と方式](../../docs/superpowers/specs/2026-10-22-local-download-storage-design.md)
- 手順: [実装計画](../../docs/superpowers/plans/2026-10-22-local-download-storage.md)
- 環境: macOS、Python 3.9.5、QGIS 3.42.1、Qt 5.15.2。QGIS 4 / Qt 6は実機未検証。

## 動作の確認

| 要件 | 証拠 |
| --- | --- |
| 保存先を初回だけ選択・以後記憶 | `test_choose_directory_remembers_and_cancel_keeps_previous`、`test_mesh_downloads_once_and_uses_local_sources` |
| ブラウザからの初回設定→再表示 | `test_browser_model_first_selection_refreshes_to_local_layers`。実BrowserModelのワーカーとGUIで確認 |
| 設定取消・不正な保存先 | `test_browser_unconfigured_offers_folder_choice_without_download`、`test_bad_directory_does_not_change_setting` |
| 右クリックから保存先変更 | `test_root_menu_can_change_directory` と実BrowserModel試験。変更後は新しい保存先のURIになり、追加済みレイヤーの参照・地物は変わらない |
| 同じ原本を再利用して通信しない | `test_download_reuses_completed_file_without_requests`。ローカルHTTPサーバーのGET回数を確認 |
| 同時取得・URLの衝突防止 | `test_same_url_concurrent_download_only_fetches_once`、`test_different_urls_with_same_filename_do_not_collide` |
| エラー時に未完成ファイルを残さない | HTTP 404、途中切断、空ファイル、HTML、破損ZIPのパラメータ化テスト。再試行の成功も確認 |
| 中止・書き込み不可 | `test_cancel_download_leaves_no_completed_file`、`test_cancel_before_request_and_unwritable_destination_do_not_download` |
| 圧縮ストリーム破損 | `test_corrupt_compressed_zip_is_reported_and_removed`。例外漏れを再現して修正 |
| HTML説明書を含む正常ZIP | `test_valid_zip_with_html_documentation_is_accepted`。レビュー指摘を失敗テストで再現して修正 |
| ローカルレイヤーを保存して開き直す | `test_browser_download_and_project_reopen_never_reconnect`。ZIP・単体GeoJSONの両方でHTTPを503にしても地物が読め、リクエスト数が増えない |
| 共有・配置変更 | `test_project_can_move_with_downloaded_archives`。通常ZIPはフォルダ移動後、入れ子ZIPは同じパスで再読込できる |
| 既存の読み込み操作 | ブラウザ・メッシュの既存回帰テスト。複数レイヤー、ラスタ、入れ子ZIP、削除後の再追加、重複抑止も確認 |

分類・データセットの一覧は同梱カタログを使う。検証では国の配布サーバーへデータ取得リクエストを送らず、ローカルHTTPと小さな試験ZIPを使用した。

## 表示の確認

実QGISのブラウザモデルをQtウィジェットで表示した確認用画像。オフスクリーン描画で、検証データを使用している。

![初回だけ保存先を選択するブラウザ項目](../../imgs/local-storage-setup.png)

## 最終チェック

```bash
source setup_qgis_env.sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q --cov=ksj --cov=scripts --cov-report=term-missing
uv run --frozen ruff check .
git diff --check
```

- 全テスト: **122 passed**（46.46秒）。既存のpytest-covとpytest間の非推奨警告2件のみ。
- カバレッジ: `ksj` と `scripts` の合計 **83%**。
- Ruff: **All checks passed**。依存関係を更新しないよう `--frozen` を使用した。
- `git diff --check`: 成功。
- 全体レビュー指摘のHTML誤判定は、失敗を再現したテストが修正後に成功。

Qtのネイティブワーカースレッドで動く部分は、この環境のPythonカバレッジに一部反映されない。取得・再利用・失敗・中止の主要経路は実HTTPの取得回数、完成ファイル、一時ファイル、レイヤーの地物をそれぞれ検証している。

## 実装上の判断と制約

- 指定フォルダは永続データの置き場とし、自動削除・自動更新をしない。公開元が同じURLの内容を差し替えても自動取得しないため、取り直し方をREADMEに記載した。
- 保存先変更では既存ファイルを移動しない。既存レイヤーが参照する元の保存先も保持する必要がある。
- 保存先変更時はブラウザの子項目を作り直す。単なるrefreshでは古いURIが残ることを実BrowserModelで再現し、子項目の破棄を追加して修正した。
- 旧バージョンで追加したリモート参照レイヤーは自動移行しない。再追加が必要。
- QGIS 3.42は入れ子ZIPのVSIパスを相対パス化しない。同じ共有パスで使うか、移動後に参照先を修正する。通常ZIPは相対パス保存・移動を確認済み。
- 全体レビューを別エージェントで実施し、HTML説明書による誤判定を修正した。推測的な単体Shapefileサイドカー問題は、現カタログの配布原本がすべてZIPであることを確認して対象外とした。
