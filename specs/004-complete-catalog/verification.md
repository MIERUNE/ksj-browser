# 全データカタログの検証記録

実施日: 2026-10-20〜21。対象環境: macOS、QGIS 3.42.1-Münster、Python 3.9.5、Qt 5.15.2。

## 収録範囲

| 公式一覧 | 項目数 |
| --- | ---: |
| [現行形式](https://nlftp.mlit.go.jp/ksj/) | 133 |
| [JPGIS1.0（XML）](https://nlftp.mlit.go.jp/ksj/jpgis/jpgis_datalist.html) | 50 |
| [旧統一フォーマット（シェープ・XML）](https://nlftp.mlit.go.jp/ksj/gmlold/index.html) | 74 |
| [旧統一フォーマット（TXT・CSV）](https://nlftp.mlit.go.jp/ksj/old/old_datalist.html) | 90 |
| 合計 | 347 |

公式一覧から詳細ページ・関連旧版を辿り、511ページと、都市計画決定情報の公開配布一覧JS（2022・2024年度）を取得した。関連旧版を5項目にまとめて追加し、ブラウザでは352項目を表示する。

- 重複を除いた配布URL: **58,101件**
- 未取得ページ・認証画面の誤登録: **0件**
- 配布ファイルが0件の表示項目: **0件**
- 同梱JSON: 353ファイル、約38.5MB。元の地理データは同梱せず、利用時に接続する。
- A26（土砂災害危険箇所）は利用者による画像認証後に47件を取得した。

取得日時やページごとの件数は [index.json](../../ksj/catalog/index.json) に記録している。

## 網羅性の独立照合

生成処理の `parse_page` を使わず、別の `HTMLParser` でキャッシュ内の `href` と `onclick` 属性を収集し、公式JSの全 `dl` プロパティも抽出した。相対パスを元ページに対して解決し、フラグメントと末尾空白以外はURLを保持して、同梱JSONのURL集合と比較した。

| 確認 | 結果 |
| --- | --- |
| 独立抽出とカタログのURL集合 | 58,101件で一致 |
| 抽出済みなのに未収録のURL | 0件 |
| 元ページに存在しない追加URL | 0件 |
| 一覧・詳細ページ内の未取得リンク先 | 0件 |
| 全ブラウザ階層から到達できる一意URL | 58,101件 |
| 兄弟ノードのパス重複 | 0件 |
| 全511ページのデータセットへの所属 | 確認済み |
| 異なる製品キーの混在 | 0件 |

現行トップの通常一覧は133項目。ランキングには旧L02-2025へのリンクもあるため、ページ全体では134種類の詳細URLがある。この旧版も収録済みであり、一覧項目として重複追加していない。

拡張子を限定しない追加監査でも、配布関数121,056箇所のパス引数はすべてZIPだった。一意な静的配布49,589件、動的配布8,511件、共通コードリスト1件の合計が58,101件と一致する。XLS／XLSX／XMLのリンクは属性定義・コード表・利用条件・公開一覧・メタデータ等の補助資料で、各版の公式ページから参照できる。

A31a（河川単位）とA31b（メッシュ単位）は区別した。識別子が異なる旧A31は関連データに独立させ、複数仕様を含む旨を表示する。年度・地域の指定がないものは補助資料 `codelists.zip` で、推測した年度や地域を補っていない。

## 実QGISでの確認

- 実際の `QgsBrowserModel` → `QgsBrowserProxyModel` → `QgsBrowserTreeView` で分類・年度・地域・配布ファイルを展開。[画面](../../imgs/catalog-browser.png)を保存。
- 公式ダムデータ [W01-14_GML.zip](https://nlftp.mlit.go.jp/ksj/gml/data/W01/W01-14/W01-14_GML.zip) をGDAL VSI経由で直接読み込み。`W01-14-g_Dam.shp` は有効、2,749地物、EPSG:6668。
- 公式土地利用ラスタ [L03-b-14_3036.zip](https://nlftp.mlit.go.jp/ksj/gml/data/L03-b_r/L03-b_r-14/L03-b-14_3036.zip) のGeoTIFFを読み込み。ラスタ用MIME・GDALプロバイダ・プロジェクト追加を確認。
- 公式標高・傾斜度 [G04-a-11_3036-jgd_GML.zip](https://nlftp.mlit.go.jp/ksj/gml/data/G04-a/G04-a-11/G04-a-11_3036-jgd_GML.zip) のShapefileを読み込み。
- 自動テストでGeoJSONの追加、入れ子ZIP内のCSV読み込み、標準GML／GeoPackageの複数レイヤー列挙・一括追加、年度の降順、市区町村別分類、部分取得失敗の個別リンクを確認。
- 旧テストの未実装・常時スキップ4件を、実QGISのブラウザ項目・追加・ドラッグ用MIME・入れ子ZIPのテストに置き換えた。

ターミナル実行のQGIS付属GDALではCA証明書探索に失敗したため、実データの接続確認時に `CURL_CA_BUNDLE=/etc/ssl/cert.pem` を指定した。証明書検証は無効化していない。

## 自動検証の実行方法

結果: **82件成功、失敗0件、スキップ0件、全体カバレッジ82%**。`ruff check .` と `git diff --check` は成功。警告2件はQGIS同梱 `pytest-cov` の非推奨フックに関するもので、テスト失敗ではない。

```bash
source setup_qgis_env.sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q \
  --cov=ksj --cov=scripts --cov-report=term-missing
uv run --frozen --no-sync ruff check .
git diff --check
```

既存の行政区域テスト3件は、現行実装と既存仕様 `specs/002-admin-area-data/spec.md` のFR-012に合わせて期待値を修正した。都道府県名を省略せず、抽出済みの `prefecture_id` も検証する。

## 検証範囲の限界

全配布ファイルのバイナリをダウンロードして内容検査したものではない。全配布URLの収録・分類・到達性を照合し、形式ごとの読み込みは代表ファイルと自動テストで確認した。公開元の削除・配布停止・認証・通信障害は、その時点の公式状況に依存する。

GDAL非対応の独自XML、旧TXT、LZH等は原本ダウンロードで利用する。標高メッシュの配布XMLも今回のGDALでは開けず、同梱Shapefileを利用できることを確認した。座標参照系が配布ファイルにない場合は推測で設定しない。

QGIS 4／Qt 6や他OSでの実行検証は行っていない。QGIS 3.42／Qt 5で確認した範囲を示す。
