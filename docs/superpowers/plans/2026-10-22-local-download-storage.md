# ローカル保存 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 初回だけ指定した保存先へ配布ファイルを取得し、以後はローカルデータから表示する。

**Architecture:** 保存先設定と原本の取得・再利用を `ksj/local_storage.py` に集約する。ブラウザおよびメッシュの入り口で保存先を確定し、レイヤー生成より前に取得を完了する。

**Tech Stack:** Python標準ライブラリ、QGIS、qgis.PyQt、GDAL、pytest。

**Spec:** `docs/superpowers/specs/2026-10-22-local-download-storage-design.md`

## Global Constraints

- Python 3.9以上、QGIS 3.40以上、追加依存なし。
- GUI操作はGUIスレッド。日本語UI・説明。パッケージ内は相対インポート。
- 新規レイヤー参照に `/vsicurl/` を残さない。既存プロジェクトは自動移行しない。

## Review Focus

- 同名ファイル・クエリ付きURLの衝突 → 保存パスの分離テスト。
- 途中切断・HTML認証画面・壊れたZIP → 完成ファイルを作らないテスト。
- ブラウザとメッシュからの同時取得 → HTTP取得1回のテスト。
- 初回選択の取消・保存先変更 → 設定保存と既存レイヤー維持のテスト。
- プロジェクトの再読み込み → HTTP停止後も地物を読めるテスト。

### Task 1: 保存先と取得・再利用

**Files:** 作成 `ksj/local_storage.py`, `tests/test_local_storage.py`。

**Interfaces:** `download_directory() -> str`, `choose_download_directory(parent=None) -> str`, `ensure_local_file(url, directory, is_canceled=None, progress=None) -> str`。

- [x] テスト: 初回設定、取消、URLごとの保存、2回目の取得0回、同時取得1回、壊れたZIP・HTML・切断・取消で完成ファイルなし。
- [x] 上記を失敗確認後、QgsSettings / QgsFileDownloader / QLockFile / 一時ファイル検証で実装。
- [x] `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_local_storage.py` が成功。

### Task 2: ブラウザとメッシュへの接続

**Files:** 変更 `ksj/browser.py`, `ksj/catalog_browser.py`, `ksj/mesh_index.py`, `ksj/zip_scanner.py` と対応テスト。

**Interfaces:** Task 1の保存先・取得関数を使用。`vsi_zip_root(local_path)` はローカル専用にする。

- [x] テスト: 未設定時の案内とGUIでの選択、右クリック変更、ZIP・単体ファイル・メッシュのローカルURI、取消、HTTP停止後のプロジェクト再読み込み。
- [x] テスト失敗後に各読み込み経路を接続し、既存モックもローカル取得境界に更新。
- [x] `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_local_storage.py tests/test_catalog_browser.py tests/test_mesh_index.py tests/test_zip_scanner.py` が成功。

### Task 3: 利用説明と最終検証

**Files:** 変更 `README.md`、作成 `specs/006-local-download/verification.md`。

- [x] 初回設定、原本の再利用、変更・更新・共有・旧プロジェクトの扱いを説明する。
- [x] 全テスト・カバレッジ、`uv run ruff check .`、UI表示とレビューを完了して記録する。
- [x] 利用者が確認できる差分として残す。コミット・公開は今回の完了要件に含めない。
