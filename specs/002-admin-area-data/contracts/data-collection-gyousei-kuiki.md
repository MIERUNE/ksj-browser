# Contract: gyousei_kuiki データコレクション定義

## ファイル

- `ksj/data_collections/gyousei_kuiki.json`

## 目的

ブラウザパネルで行政区域データを「年度 → 地域 →ZIP 内ファイル」として表示するためのマッピングを提供する。

## JSON 構造

- ルート: オブジェクト
- キー: `YYYY年`
- 値: 地域 →ZIP ファイル名のオブジェクト

### 例

```json
{
	"2025年": {
		"全国": "N03-20250101_GML.zip",
		"北海道": "N03-20250101_01_GML.zip"
	}
}
```

## 制約

- 年度キーは 4 桁年＋`年`
- 地域キーは既存コレクション表記（原則サフィックス無し）
- 値は `*.zip` のファイル名（相対 URL ではない）
- 同一年・同一地域に複数候補がある場合、`*_SHP.zip` を優先し、無ければ `*_GML.zip`

## 互換性

- 既存の `load_data_collections()` の読み込み形式（`dict[str, dict[str, dict[str, str]]]`）と互換
