# Quickstart: Zip 再帰探索ブラウズ

## 前提

- QGIS 3.x（macOS の場合は /Applications/QGIS.app）
- `uv` を利用できること
- pytest-qgis を動かすために、QGIS ライブラリへの環境変数設定が必要（macOS）

## 開発環境セットアップ

- 仮想環境（例）:
  - `uv venv --python /Applications/QGIS.app/Contents/MacOS/bin/python3 --system-site-packages`
  - `uv sync`

## テスト実行

- macOS:
  - `source setup_qgis_env.sh`
  - `uv run python -m pytest -v`

## 受入テスト用 ZIP の入力

- 受入テストの ZIP セットは `ksj/data_collections/*.json` に記載されている ZIP 名を使用する
- ただし、ネットワーク依存の統合テストは環境により不安定になり得るため、デフォルトではモック中心のテスト構成とし、必要に応じて統合テストを有効化する（具体化は tasks で決める）

## 動作確認（QGIS）

- QGIS のブラウザパネルで「国土数値情報（KSJ）」配下にコレクションが表示されること
- 年度 → 都道府県を展開すると、ZIP 内のフォルダ/ファイルが表示されること
- `.shp` / `.geojson` をダブルクリックするとレイヤが追加されること
