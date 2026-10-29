# Repository Guidelines

## プロジェクト構成とモジュール
プラグイン本体は `ksj/` 直下にあり、プロバイダ (`browser.py`)、ブラウザ項目 (`catalog_browser.py`)、カタログ読み込み (`catalog.py`)、保存・解凍 (`local_storage.py`)、ファイル探索 (`zip_scanner.py`)、メッシュ索引 (`mesh_index.py`)、文字コード判定 (`encoding_check.py`)、通知 (`messages.py`)、一時ディレクトリ (`temporary_files.py`) が中心です。全データ定義は `ksj/catalog/*.json`、アイコンは `ksj/icons/`、仕様書は `specs/`、更新スクリプトは `scripts/` に配置され、`imgs/` にはドキュメント用画像を置きます。`plugin.py` と `__init__.py` が QGIS ローダーを構成し、`setup_qgis_env.sh` が macOS 開発環境を初期化します。

## ビルド・テスト・開発コマンド
テストは Docker を標準とし、`bash scripts/test-docker.sh` で全テストとカバレッジを実行します。既定の QGIS は 3.44 です。`QGIS_TEST_IMAGE=qgis/qgis:4.2-trixie bash scripts/test-docker.sh` でバージョンを切り替え、`bash scripts/test-docker.sh tests/test_catalog.py -q` で対象を絞れます。テスト依存は `requirements-test.txt` でバージョン固定しており、コンテナ内とホスト手順の両方がこのファイルを使います。GitHub Actions は同じスクリプトで QGIS 3.44・4.0・4.2 を確認します。リリースは `v<version>` の GitHub Release を公開すると `release.yaml` がタグの版（`v` を除いた値）を `scripts/build-plugin-zip.sh` で配布 ZIP の `metadata.txt` に書き込み（リポジトリの `metadata.txt` は `version={{PLUGIN_VERSION}}` のまま）、配布 ZIP（直下は `ksj_browser/`）を作って Release に添付し、シークレット `QGIS_PLUGIN_TOKEN` があれば plugins.qgis.org に投稿します。Lint は `uv sync --locked` の後、`uv run --no-sync ruff check .`・`uv run --no-sync ruff format --check .`・`uv run --no-sync bandit -c pyproject.toml -l -r .` を実行します。bandit は plugins.qgis.org のアップロード時スキャンに合わせて重大度 Low 以上の全件で失敗し、`tests/`・`scripts/` などは `pyproject.toml` の `[tool.bandit]` で除外しています。`pyproject.toml` は配布 ZIP に入らずサイトの検査には効かないため、除外以外の設定（`skips` など）で指摘を抑えずにコードを直してください。Qt6 互換は README の「Qt6 互換チェック」のコマンド（`ghcr.io/qgis/pyqgis4-checker:main-ubuntu` の `pyqt5_to_pyqt6.py --dry_run`）で確認し、CI の Lint ワークフローでも同じチェックを行います。対応バージョンは QGIS 3.44 以上 4.x までで、`metadata.txt` の `qgisMinimumVersion`・`qgisMaximumVersion` で宣言します。

ホスト側の QGIS を使う場合は、QGIS 付属 Python で仮想環境を作成します。
```
uv venv --python /Applications/QGIS.app/Contents/MacOS/bin/python3 --system-site-packages
```
テスト依存は `uv pip install --python .venv/bin/python -r requirements-test.txt` で入れ、テストは `source setup_qgis_env.sh && .venv/bin/python -m pytest -v` で環境変数込みで実行します。迅速な確認は `.venv/bin/pytest tests/ -v`、被覆率確認は `.venv/bin/pytest tests/ --cov=ksj --cov=scripts --cov-report=term-missing` を使います。カタログ更新時は `python3 scripts/update_catalog.py --refresh` を走らせて全データの JSON を再生成してください。

## コーディングスタイルと命名規則
Python の 4 スペースインデント、`snake_case` モジュール、`CamelCase` クラス、`UPPER_SNAKE_CASE` 定数を徹底します。パッケージ内部では `from .child import Child` のように相対インポートを使い、Plugin Reloader のリロード互換性を保ちます。コミット前に `uv run ruff check .` を実行し、`pyproject.toml` で管理されるフォーマット・Lint 規約に従ってください。

## テスト指針
`pytest` と `pytest-qgis` が標準です。対象モジュールに対応した `test_<module>.py` を `tests/` に追加し、QGIS ウィジェットを扱う場合はフィクスチャで待機管理を行います。バグ修正やデータ更新では回帰テストとカバレッジレポートを必ず確認し、`ksj` と `scripts` の主要経路を網羅してください。

## コミットと Pull Request
履歴は `feat: Add support for administrative area data` や `fix: タスクリストの表記を修正` のような Conventional Commits 形式です。タイプは小文字、要約は 50 文字程度に収め、必要なら日本語本文で詳細を補います。Pull Request では影響範囲、テスト結果 (`pytest` コマンド等)、関連仕様 (`specs/00x-*`) や更新した JSON の記載、UI 変更時のスクリーンショットを添付してください。1 PR につき 1 トピックを守り、レビュワーが追いやすい粒度に分割します。

## QGIS 環境とセキュリティ
GDAL VSI で公共 ZIP にアクセスするため資格情報は不要ですが、私的 URL や API キーをリポジトリに含めないでください。システムサイトパッケージ共有の仮想環境にのみ依存し、`pip install PyQt5` など QGIS と競合するパッケージは避けます。大きな半径の円など CRS 依存ロジックはローカル投影へ変換してから処理するのが安全です。

## コミュニケーション
Issue、Pull Request、レビューコメント、ドキュメント更新時の説明はすべて日本語で記述してください。自動応答やエージェント出力も日本語で統一し、利用者が即座に理解できる表現を心掛けましょう。

## Active Technologies
- Python 3.9以上、QGIS/PyQt/GDAL、標準ライブラリ、カタログ収集用curl
- JSON ファイル (`ksj/catalog/index.json` とデータセット別JSON)

## Recent Changes
- 全件カタログへの移行に伴い旧3コレクションのコード・JSON・更新スクリプトを廃止。
- `specs/001-*`〜`specs/003-*` は移行前の設計履歴。現行構成・更新方法は README と `specs/004-complete-catalog/` 以降を参照。
- kumoy 連携（`ksj/kumoy_upload.py`）は `ENABLED = False` で利用者向けに無効化中。復活時はフラグを真にし、README の説明と `imgs/loading-settings.png` を戻す（`docs/superpowers/specs/2026-10-27-kumoy-disabled-design.md`）。
