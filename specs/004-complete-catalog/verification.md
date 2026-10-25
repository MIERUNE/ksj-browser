# 全データカタログの検証記録

実施日: 2026-10-20〜21。対象環境: macOS、QGIS 3.42.1-Münster、Python 3.9.5、Qt 5.15.2。

## 移行後の整理（2026-10-22）

- 旧 `data_loader.py` と3コレクションJSON、専用更新スクリプト3本、専用テスト4本・HTMLフィクスチャ2本、空の `ui/__init__.py` を削除した。実行コードからの参照がないこと、旧JSONの配布ファイル名2,113件（土砂災害警戒区域530件・行政区域1,423件・学校160件）がすべて現行カタログに含まれることを削除前に照合した。
- 更新経路を `scripts/update_catalog.py` に統一し、README・AGENTS・WARPを現行構成に合わせた。旧仕様書は設計履歴として残す。以下の旧コレクション・テストに関する記載は移行時点の記録であり、現行の運用手順ではない。
- [Issue #4](https://github.com/MIERUNE/ksj-browser/issues/4): 索引を含めた全JSONの書き込み成功後だけ、出力先直下の孤児JSONを削除する。取得失敗・データセット書き込み失敗・索引書き込み失敗では削除しない。非JSONファイルとサブディレクトリは保持する。
- 回帰テストで修正前の `stale.json` 残存を再現し、修正後の削除を確認した。同梱JSONと索引のファイル集合を照合するテストも追加した。現行352データセット・353JSONに孤児や欠落はなく、収録内容は変更していない。
- QGIS付属Python 3.9.5で全テスト **110件成功・失敗0件・スキップ0件、カバレッジ84%**。実行コマンドは下記の自動検証と同じ。ローカルHTTPサーバーを使うテストはサンドボックス外で実行した。警告3件は既存のpytest-cov非推奨フック2件と重複ZIP名のテスト1件。
- `uv run --frozen --no-sync ruff check .` と `git diff --check` は成功。

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

結果: **85件成功、失敗0件、スキップ0件、全体カバレッジ83%**。`ruff check .` と `git diff --check` は成功。警告2件はQGIS同梱 `pytest-cov` の非推奨フックに関するもので、テスト失敗ではない。

```bash
source setup_qgis_env.sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q \
  --cov=ksj --cov=scripts --cov-report=term-missing
uv run --frozen --no-sync ruff check .
git diff --check
```

既存の行政区域テスト3件は `main` 時点で既に失敗していた。`normalize_region()` が引数をそのまま返す恒等関数であるのに対し、テストが `青森県 → 青森` を期待していたためである。本変更では現行実装に合わせて期待値を修正し、抽出済みの `prefecture_id` も検証対象に加えた。

なお `specs/002-admin-area-data/spec.md` FR-012 の例（`青森県`・`東京都`）は、同梱している `ksj/data_collections/*.json` の実際のキー（`青森`・`東京`、3コレクションとも同形式）とも `specs/003-school-data/spec.md` FR-012（`青森`）とも一致していない。修正後のテストは恒等関数の確認にとどまり、FR-012自体は検証していない。この矛盾は本変更のスコープ外であり、仕様・実装・データの表記統一は [#5](https://github.com/MIERUNE/ksj-browser/issues/5) で扱う。

## レビュー指摘への対応

PR #1 のコードレビューを受けて、次の2点を本変更に取り込んだ。

- `ksj/catalog_browser.py`: 分類・データセット・市区町村・配布ファイルの各ノードに `sortKey` を設定した。`QgsDataItem::sortKey()` は未設定時に `name()` を返すため、設定しないと公式一覧の掲載順が表示名のコードポイント順に崩れる（例: 水域が「海岸線／湖沼／ダム／河川」ではなく「ダム／河川／湖沼／海岸線」になる）。
- `ksj/catalog_browser.py` の `archive_children()`: `ZipScanError` に加えて想定外の例外も捕捉し、エラーノードとして表示するようにした。旧 `KsjPrefectureItem` が持っていた包括捕捉が移行時に失われており、GDAL由来の例外がブラウザのワーカースレッドへ抜ける状態だった。

いずれも回帰テストを追加済みで、修正前は4件が失敗し、修正後は全件成功することを確認している。

本変更には取り込まず、Issueで追跡する指摘は次のとおり。

- [#2](https://github.com/MIERUNE/ksj-browser/issues/2) 画像認証ページの検出がUTF-8のページでしか機能していない
- [#3](https://github.com/MIERUNE/ksj-browser/issues/3) ZIP内の非空間XML・CSVがレイヤー候補として並ぶ量の実データ確認
- [#4](https://github.com/MIERUNE/ksj-browser/issues/4) カタログ再生成時に古いデータセットJSONが削除されない
- [#5](https://github.com/MIERUNE/ksj-browser/issues/5) 都道府県名キーの表記が仕様・データ間で食い違っている

## 検証範囲の限界

全配布ファイルのバイナリをダウンロードして内容検査したものではない。全配布URLの収録・分類・到達性を照合し、形式ごとの読み込みは代表ファイルと自動テストで確認した。公開元の削除・配布停止・認証・通信障害は、その時点の公式状況に依存する。

GDAL非対応の独自XML、旧TXT、LZH等は原本ダウンロードで利用する。標高メッシュの配布XMLも今回のGDALでは開けず、同梱Shapefileを利用できることを確認した。座標参照系が配布ファイルにない場合は推測で設定しない。

QGIS 4／Qt 6や他OSでの実行検証は行っていない。QGIS 3.42／Qt 5で確認した範囲を示す。
