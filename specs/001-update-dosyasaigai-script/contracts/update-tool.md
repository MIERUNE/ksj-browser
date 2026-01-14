# Contract: 土砂災害警戒区域データ更新ツール

## 目的

A33（土砂災害警戒区域）の公開ページから年度×地域の ZIP ファイル一覧を取得し、`dosyasaigai_keikai_kuiki.json` を最新化する。

## 入力

- デフォルト URL: https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A33-2024.html
- `--url <URL>`: 任意 URL に切り替え
- `--html-file <PATH>`: ローカル HTML（指定時は唯一のソース）
- `--output <PATH>`: JSON 出力先

## 出力

- `ksj/data_collections/dosyasaigai_keikai_kuiki.json`（UTF-8, pretty-print）
- 標準出力: 抽出行数・年度数・地域数サマリ
- 終了コード: 0/1/2/3（成功/ネットワーク/パース/書込み）

## 振る舞い

1. 入力ソースを決定（`--html-file` があれば最優先）
2. HTML を解析し、テーブルから「年」「地域」「ファイル名」を抽出
3. 年度と地域名を正規化
4. 同年度・地域に複数ファイルがある場合 `_SHP.zip` を優先し、無ければ `_GML.zip`
5. JSON を年度降順、地域名 50 音順で書き出す
6. 失敗時はエラーメッセージと対応コードで終了

## 期待されるログ

- INFO: 取得先 URL または HTML ファイルパス
- INFO: 抽出行数、対象年度数、書き込み先
- ERROR: ネットワーク/パース/書込み失敗の詳細
