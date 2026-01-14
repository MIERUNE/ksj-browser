# Research: 学校データのサポート追加

**Date**: 2026-01-14  
**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Research Tasks

以下の不明点を調査し、実装の意思決定に必要な情報を収集する。

### 1. P29（学校）データの HTML テーブル構造

**Question**: P29 の HTML テーブル構造は N03（行政区域）と同じか？

**Findings**:

調査結果：P29 のテーブル構造は N03 と**ほぼ同一**であることを確認。

```html
<table class="mapjpn1 mb15 responsive-table">
	<tbody>
		<tr>
			<th>地域</th>
			<th>測地系</th>
			<th>年</th>
			<th>ファイル容量</th>
			<th>ファイル名</th>
			<th>ダウンロード</th>
		</tr>
		<tr>
			<td id="prefecture0">全国</td>
			<td class="txtCenter">世界測地系</td>
			<td class="txtCenter">2023年（令和5年）</td>
			<td class="txtCenter">1.13MB</td>
			<td class="txtCenter">P29-23_GML.zip</td>
			...
		</tr>
		<tr>
			<td id="prefecture1">北海道</td>
			<td class="txtCenter">世界測地系</td>
			<td class="txtCenter">2023年（令和5年）</td>
			<td class="txtCenter">5.19MB</td>
			<td class="txtCenter">P29-23_01_GML.zip</td>
			...
		</tr>
	</tbody>
</table>
```

**Decision**: `update_gyousei_kuiki.py` の `N03TableParser` クラスを参考に、P29 用のパーサーを作成する。カラム順序とクラス名は同一のため、ほぼ流用可能。

**Rationale**: 同一のテーブル構造を持つため、既存のパーサーロジックを最小限の変更で再利用できる。開発効率と保守性が向上する。

---

### 2. P29 の URL 構造とディレクトリ命名規則

**Question**: P29 データのダウンロード URL ディレクトリ構造はどうなっているか？

**Findings**:

実際の URL 例（HTML 内 onclick 属性から確認）:

- 全国: `../data/P29/P29-23/P29-23_GML.zip`
- 北海道: `../data/P29/P29-23/P29-23_01_GML.zip`

URL パターン:

- ベース: `https://nlftp.mlit.go.jp/ksj/gml/data/P29/P29-{YY}/{FILENAME}`
- `{YY}`: ファイル名の年部分（2 桁）を使用（例: `P29-23` → `23`）
- `{FILENAME}`: テーブル上のファイル名をそのまま使用

**既存データとの比較**:

| データ ID       | ディレクトリ構造  | 年の決定方法                              |
| --------------- | ----------------- | ----------------------------------------- |
| A33（土砂災害） | `A33/A33-{YY}/`   | ファイル名から 2 桁年を抽出               |
| N03（行政区域） | `N03/N03-{YYYY}/` | 入力年から 4 桁年を使用                   |
| **P29（学校）** | `P29/P29-{YY}/`   | ファイル名から 2 桁年を抽出（A33 と同じ） |

**Decision**: P29 は A33 と同じ戦略（ファイル名から 2 桁年抽出）を使用する。既存の `_get_dir_year_from_filename_yy()` 関数を再利用し、`_DIR_YEAR_STRATEGIES` 辞書に `P29` を追加する。

**Rationale**: P29 は A33 と同じパターンを持つため、既存の戦略をそのまま適用できる。新しいロジックを追加する必要がなく、実装コストが最小化される。

---

### 3. 地域名の正規化規則

**Question**: P29 の地域名表記は N03 や A33 と統一されているか？正規化が必要か？

**Findings**:

P29 の地域名表記（確認した例）:

- 全国
- 北海道
- 東北地方
- 青森
- 岩手
- ...

N03 の地域名表記（既存 JSON より）:

- 全国
- 北海道
- 東北地方
- 青森
- 岩手
- ...

**Decision**: P29 と N03 の地域名表記は一致している。`update_gyousei_kuiki.py` の `normalize_region()` 関数をそのまま流用する。

**Rationale**: 既存の正規化ロジック（都道府県接尾辞の削除、「東京」「京都」「北海道」の特殊処理）が P29 にも適用できる。コードの重複を避け、一貫性を保つ。

---

### 4. 配布形式（SHP / GML）の判定方法

**Question**: P29 データは SHP と GML の両方が提供されるか？どちらを優先すべきか？

**Findings**:

2023 年度版の P29 ページを調査した結果:

- **GML のみ**が提供されている（例: `P29-23_GML.zip`, `P29-23_01_GML.zip`）
- SHP 版は確認できなかった

**ファイル名パターン**:

- GML: `P29-{YY}_{REGION}_GML.zip` または `P29-{YY}_GML.zip`（全国）
- SHP: （今回は存在しないが、将来的には `P29-{YY}_{REGION}.zip` の可能性）

**Decision**:

1. フィルタリング時は SHP（`.zip` で `_GML` を含まない）を優先
2. SHP が存在しない場合は GML（`_GML.zip`）を採用
3. `update_gyousei_kuiki.py` の `deduplicate_by_format()` ロジックをそのまま流用

**Rationale**: 既存の N03 と同じ方針を採用することで、将来的に P29 で SHP が提供された場合にも対応できる。現状は GML のみなので、実質的には全て GML が選択される。

---

### 5. 年度表記の正規化（和暦 → 西暦）

**Question**: P29 の年度表記は和暦か西暦か？正規化が必要か？

**Findings**:

P29 の年度表記（HTML より）:

- `2023年（令和5年）`

既存の `normalize_year()` 関数（`update_gyousei_kuiki.py` より）:

- 西暦優先で抽出（4 桁数字を検出）
- 西暦がない場合は和暦から変換

**Decision**: `normalize_year()` 関数をそのまま流用する。P29 は西暦が先頭にあるため、自動的に `2023年` として抽出される。

**Rationale**: 既存の関数が P29 のフォーマットに対応している。追加実装不要。

---

### 6. データコレクション ID と表示名

**Question**: 学校データのコレクション ID と表示名はどうすべきか？

**Findings**:

既存のコレクション ID 規則:

- `dosyasaigai_keikai_kuiki` → 「土砂災害警戒区域」
- `gyousei_kuiki` → 「行政区域」

P29 データの正式名称:

- 「学校」（国土数値情報の公式ページより）

**Decision**:

- コレクション ID: `gakkou`（ローマ字、スネークケース不要な単語）
- 表示名: 「学校」
- ファイル名: `gakkou.json`

**Rationale**:

- 既存の命名規則に従い、シンプルで分かりやすい ID を採用
- 表示名は公式の日本語名称を使用
- ファイル名は ID に対応させて一貫性を保つ

---

### 7. テストの既存実装からの学習

**Question**: `update_gyousei_kuiki.py` のテストはどのように実装されているか？

**Findings**:

既存テスト（`tests/test_update_gyousei_kuiki.py`）の構造:

1. `normalize_year()` の単体テスト（和暦 → 西暦変換）
2. `normalize_region()` の単体テスト（地域名正規化）
3. `extract_table_rows()` の HTML パーステスト（フィクスチャ使用）
4. E2E テスト（実際の URL からの取得、ただしオプショナル）

**Decision**:

- `test_update_gakkou.py` を作成し、同様の構造を採用
- フィクスチャとして P29 の HTML サンプルを用意（`tests/fixtures/p29_sample.html`）
- 単体テストを優先し、E2E テストはオプショナルとする

**Rationale**: 既存のテスト方針に従うことで、保守性と一貫性を保つ。フィクスチャを使用することで、ネットワーク不要の高速なテストを実現。

---

## Summary of Decisions

| 項目             | 決定内容                                                  |
| ---------------- | --------------------------------------------------------- |
| HTML パーサー    | N03 のパーサークラスを参考に P29 用を作成（ほぼ流用可能） |
| URL 構造         | A33 と同じ戦略（ファイル名から 2 桁年抽出）を使用         |
| 地域名正規化     | N03 の `normalize_region()` をそのまま流用                |
| 配布形式優先順位 | SHP 優先、なければ GML（現状は GML のみ）                 |
| 年度正規化       | N03 の `normalize_year()` をそのまま流用                  |
| コレクション ID  | `gakkou`（表示名: 「学校」、ファイル名: `gakkou.json`）   |
| テスト戦略       | N03 と同じ構造（単体テスト + フィクスチャ）               |

## Technical Alternatives Considered

### Alternative 1: 汎用的な HTML パーサーの作成

**Description**: N03 と P29 で共通のパーサークラスを作成し、設定で切り替える。

**Rejected Because**:

- 現時点では 2 つのデータソースのみで、過度な抽象化はオーバーエンジニアリング
- 将来的に異なる構造のデータが増えた場合に対応できない可能性
- YAGNI（You Aren't Gonna Need It）原則に反する

**Decision**: 各データソースごとに専用のスクリプトを作成し、必要に応じて共通関数を抽出する方針を継続。

---

### Alternative 2: データベースを使用した定義管理

**Description**: JSON ファイルではなく SQLite などのデータベースで定義を管理。

**Rejected Because**:

- QGIS プラグインは Git リポジトリで配布されるため、JSON ファイルの方が扱いやすい
- データ構造がシンプルで、データベースの複雑性は不要
- 既存の実装との一貫性を保つため

**Decision**: JSON ファイルによる管理を継続。

---

### Alternative 3: Web スクレイピングライブラリ（BeautifulSoup 等）の使用

**Description**: 標準ライブラリの `html.parser.HTMLParser` ではなく、外部ライブラリを使用。

**Rejected Because**:

- QGIS 3.28 同梱の Python 環境に追加依存を持ち込みたくない
- 標準ライブラリのみで十分対応可能
- 既存の `update_gyousei_kuiki.py` と同じ方針を維持

**Decision**: 標準ライブラリの `html.parser.HTMLParser` を使用。
