# Data Model: 行政区域データ（gyousei_kuiki）

## 目的

行政区域データの「年度 × 地域 → 配布 ZIP ファイル名」を、既存コレクションと同じ形で保持し、ブラウザパネルのツリー表示に供給する。

## Entity: DataCollectionDefinition

- **collection_id**: `gyousei_kuiki`（固定）
- **storage**: JSON ファイル（同梱）
- **shape**:

```json
{
	"2025年": {
		"全国": "N03-20250101_GML.zip",
		"北海道": "N03-20250101_01_GML.zip",
		"青森": "N03-20250101_02_GML.zip"
	},
	"2024年": {
		"全国": "N03-20240101_GML.zip",
		"北海道": "N03-20240101_01_GML.zip"
	}
}
```

## フィールド/バリデーション

- 年度キー: `^\d{4}年$`
- 地域キー: 既存コレクション表記（原則サフィックス無し、例外として `北海道` は維持）
- ファイル名: `*.zip` で終わる
- 形式選択: 同一年・同一地域に複数候補がある場合は `*_SHP.zip` を優先し、無ければ `*_GML.zip`

## 関係/派生

- ブラウザ表示: `年度` → `地域` → （ZIP 内の GIS ファイル階層）
- ダウンロード URL: `collection_id` と `年度` と `ファイル名` から構成
  - データ ID ごとのディレクトリ年決定戦略を適用（N03: 入力年から 4 桁、A33 等: ファイル名から抽出）
  - 戦略は辞書で管理し、新規データ ID 追加時は辞書への登録のみで対応可能

## 状態遷移

- `source page updated` → `dev tool run` → `gyousei_kuiki.json updated` → `commit` → `plugin uses updated definition`
