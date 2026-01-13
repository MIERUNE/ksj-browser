# Repository Guidelines

## プロジェクト構成とモジュール
プラグイン本体は `ksj/` 直下にあり、ブラウザ項目 (`browser.py`)、ZIP 解析 (`zip_scanner.py`)、データ読み込み (`data_loader.py`)、および `ksj/data_collections/*.json` で定義されるコレクション設定が中心です。UI リソースは `ui/`、仕様書は `specs/`、開発補助スクリプトは `scripts/` に配置され、`imgs/` にはドキュメント用画像を置きます。`plugin.py` と `__init__.py` が QGIS ローダーを構成し、`setup_qgis_env.sh` が macOS 開発環境を初期化します。

## ビルド・テスト・開発コマンド
QGIS 付属 Python で仮想環境を作成します。
```
uv venv --python /Applications/QGIS.app/Contents/MacOS/bin/python3 --system-site-packages
```
テストは `source setup_qgis_env.sh && uv run python -m pytest -v` で環境変数込みで実行し、迅速な確認は `.venv/bin/pytest tests/ -v`、被覆率確認は `.venv/bin/pytest tests/ --cov=ksj --cov=scripts --cov-report=term-missing` を使います。行政区域データ更新時は `python scripts/update_gyousei_kuiki.py` を走らせて JSON を再生成してください。

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
