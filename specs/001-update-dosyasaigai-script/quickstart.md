# Quickstart: 土砂災害警戒区域データ更新ツール

このガイドは `dosyasaigai_keikai_kuiki.json` を最新化し、QGIS での動作確認を行う手順をまとめたものです。

## 1. ツール実行

```bash
python scripts/update_dosyasaigai_keikai_kuiki.py
```

### 主なオプション

| オプション | 説明 |
|------------|------|
| `--url <URL>` | 取得元 A33 ページを上書き（デフォルト: https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A33-2024.html） |
| `--html-file <PATH>` | ローカル HTML を入力に使用。指定時はネットワークアクセスを行わない |
| `--output <PATH>` | 出力先 JSON を上書き（デフォルト: ksj/data_collections/dosyasaigai_keikai_kuiki.json） |

### 終了コード

- 0: 成功
- 1: ネットワーク取得失敗（HTTP/URL エラー）
- 2: テーブル未検出または必須列欠落
- 3: JSON 書込み失敗

## 2. 生成物チェック

1. `ksj/data_collections/dosyasaigai_keikai_kuiki.json` が更新されていること
2. 年度キーが `YYYY年` で降順に並んでいること
3. 各年度に 47 都道府県分（必要に応じて全国）が存在すること
4. `_SHP.zip` が存在する場合はそれが選択されていること

## 3. QGIS での確認

1. `source setup_qgis_env.sh` で環境変数をセット
2. QGIS を起動し、ブラウザパネル → 「国土数値情報（KSJ）」を展開
3. 「土砂災害警戒区域」コレクションで任意の年度を展開
4. 道府県ノードを展開し、ZIP 内の `.shp` / `.gml` が列挙されることを確認
5. ファイルをダブルクリックしてマップに追加し、表示できることを確認

## 4. テスト

```bash
.venv/bin/pytest tests/test_update_dosyasaigai_keikai_kuiki.py -v
.venv/bin/pytest tests/test_data_loader.py -v -k "dosyasaigai"
```

- HTML パーステスト: 指定した HTML から年度・地域・ファイル名が抽出される
- フォーマット選択テスト: SHP 優先ルールが守られる
- URL 生成再確認: `build_download_url()` が A33 データを正しく指す

## 5. トラブルシューティング

| 症状 | 対処 |
|------|------|
| ネットワークエラー | URL、プロキシ設定の確認。`--html-file` で再現 |
| テーブル未検出 | ページ構造変更を疑い、HTML を保存して解析。`N03` スクリプトとの共通実装を比較 |
| JSON が空になる | スクリプト実行ログで「抽出行数」「年度数」を確認。0 の場合は HTML 入力を再チェック |
| QGIS で ZIP が展開できない | ファイル名が正しいか、`build_download_url()` ロジックが最新かを `pytest` で確認 |
