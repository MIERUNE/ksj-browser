# Quickstart: 行政区域データ（gyousei_kuiki）

## 1. 定義ファイルの更新

- 目的: 国土数値情報の N03 ページから最新の一覧を取り込み、`gyousei_kuiki.json` を更新する
- 実行: `python scripts/update_gyousei_kuiki.py`

## 2. 生成物の確認

- `ksj/data_collections/gyousei_kuiki.json` が更新され、年度キーが `YYYY年`、地域キーが既存表記になっていること

## 3. QGIS での確認

- ブラウザパネルで「国土数値情報（KSJ）」→「行政区域」→ 年度 → 地域 を展開し、対象ファイルが表示されること

## 4. テスト

- QGIS 環境を用意した上で `pytest` を実行し、URL 生成・拡張子フィルタ・定義読み込みが回帰していないことを確認する
