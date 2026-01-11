# Research: 行政区域データのサポート追加

## データ更新ツール（Web 抽出）

- Decision: HTML を Python 標準ライブラリのみで取得・抽出する（`urllib.request` + `html.parser.HTMLParser`）
- Rationale: 追加依存を増やさずに開発者ツールを提供でき、QGIS 同梱環境との差分も小さい。HTML 内のテーブルは静的に埋め込まれており、`<tbody><tr><td>` の抽出で要件（地域/年/ファイル名）を満たせる。
- Alternatives considered:
  - BeautifulSoup/requests: 実装は容易だが、依存追加が必要
  - 正規表現のみ: 壊れやすく保守負荷が高い
  - ヘッドレスブラウザ: 過剰でメンテ対象が増える

## 対象テーブルの特定

- Decision: ページ内の「地域/年/ファイル名」列を含むデータ一覧テーブル（`table.dataTables`）の `tbody` を対象にする
- Rationale: ページには複数の `table` があるため、列名で特定するのが最も堅牢。DOM 上の `DataTables_Table_0_wrapper` は JS 生成の可能性があり、静的 HTML 上に存在しないケースに依存しない。
- Alternatives considered:
  - 特定の id に依存: 静的 HTML に無い場合に壊れる
  - 行番号/固定位置: レイアウト変更に弱い

## 年度の正規化

- Decision: 表示値（例: `2025年（令和7年）`）から 4 桁年を抽出し、キーは `YYYY年` に統一する
- Rationale: 既存コレクションのキー形式（`2024年`）と一致させ、UI/既存コードの前提を壊さない。
- Alternatives considered:
  - 元文字列をそのままキーにする: 年度キーが冗長で比較/ソートしにくい

## 地域名キーの正規化

- Decision: 既存コレクションと同じ表記に正規化する（原則サフィックス無し）
- Rationale: `dosyasaigai_keikai_kuiki.json` と同じ「都道府県名」キーで扱える。具体的には `…都/…府/…県` の末尾 1 文字を落とす（`北海道` の `道` は落とさない）。
- Alternatives considered:
  - 公式表記（都/道/府/県付き）: 既存コレクションとキーが揃わず、UI 上の見え方も変わる
  - コード（01,13…）: 既存データと不整合

## SHP/GML の選択

- Decision: 同一年・同一地域に複数形式がある場合は SHP を優先し、無い場合のみ GML を採用する
- Rationale: 既存の読み込みフロー（zip 内の GIS ファイルを列挙して読み込む）との親和性が高い。N03 は現状 GML のみ想定だが将来の SHP 提供にも追随できる。
- Alternatives considered:
  - 常に GML: 読み込み負荷/互換性の揺れが出やすい
  - 両方保持: UI/定義が複雑化する

## ダウンロード URL 規則（N03）

- Decision: N03 は「年(YYYY)」からディレクトリ `N03-YYYY` を構成し、URL は `.../data/N03/N03-YYYY/<filename>` とする
- Rationale: N03 のファイル名には `06` / `071001` / `20250101` 等の揺れがあり、ファイル名からディレクトリ年を安定復元できない。ページの「年」列が最も信頼できる。
- Alternatives considered:
  - ファイル名から年を推測: 推測不能なパターンがある
  - コレクションごとに完全固定 URL: 年次追加のたびに修正が必要

## URL 生成ロジックの拡張性

- Decision: ディレクトリ年の決定ロジックを戦略パターンで実装し、データ ID ごとの戦略を辞書で管理する
- Rationale: 20 以上のコレクション追加を想定すると、if/elif の連鎖は保守困難。戦略を関数として切り出し、データ ID をキーとした辞書で管理することで、新規追加時は 1 行追加するだけで済む。
- Alternatives considered:
  - if/elif 連鎖: 20 個を超えると可読性・保守性が低下
  - データ駆動（設定ファイル）: 現時点では過剰、戦略関数で十分

## ZIP 内ファイルのサポート拡張

- Decision: ZIP 走査の対象拡張子に `.gml` を追加する
- Rationale: N03 は GML が主であるため、現状の `.shp/.geojson` 固定ではブラウザ上で「対象データなし」になり利用できない。
- Alternatives considered:
  - GML は未対応（SHP のみ）: N03 が実質使えない
  - 事前にローカル変換（GML→ 別形式）: 運用が複雑化する

## リスク/注意点

- Decision: まずは「ZIP 内の `.gml` をファイルとして表示・読み込み」を最小実装とし、複数レイヤの扱いは将来の改善点として扱う
- Rationale: GML が複数レイヤ（複数 FeatureType）を含む場合、レイヤ指定が必要になる可能性があるが、現時点では仕様外の UI 拡張を避ける。
- Alternatives considered:
  - GML レイヤ一覧をブラウザで展開: UI/実装が増える
