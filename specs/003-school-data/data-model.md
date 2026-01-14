# Data Model: 学校データのサポート追加

**Date**: 2026-01-14  
**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Overview

学校データ（P29）のコレクション定義は、既存の行政区域データ（N03）と同じ JSON 構造を採用します。

## JSON Schema

### Collection Definition File: `gakkou.json`

```json
{
	"<YEAR>": {
		"<REGION>": "<FILENAME>"
	}
}
```

**フィールド説明**:

- `<YEAR>`: 年度キー（例: `2023年`）
- `<REGION>`: 地域キー（正規化済み、例: `北海道`, `青森`, `全国`）
- `<FILENAME>`: ZIP ファイル名（例: `P29-23_01_GML.zip`）

### Example

```json
{
	"2023年": {
		"全国": "P29-23_GML.zip",
		"北海道": "P29-23_01_GML.zip",
		"東北地方": "P29-23_52_GML.zip",
		"青森": "P29-23_02_GML.zip",
		"岩手": "P29-23_03_GML.zip",
		"宮城": "P29-23_04_GML.zip"
	},
	"2021年": {
		"全国": "P29-21_GML.zip",
		"北海道": "P29-21_01_GML.zip",
		"青森": "P29-21_02_GML.zip"
	}
}
```

## Data Normalization Rules

### Year Normalization

**Input**: `2023年（令和5年）` または `令和5年`  
**Output**: `2023年`

**Rules**:

1. 西暦（4 桁数字）があれば優先的に抽出
2. 西暦がない場合は和暦を西暦に変換
3. 「年」接尾辞を維持

**Implementation**: `normalize_year()` 関数（`update_gyousei_kuiki.py` から流用）

### Region Normalization

**Input**: `北海道`, `青森県`, `東京都`, `京都府`  
**Output**: `北海道`, `青森`, `東京`, `京都`

**Rules**:

1. 「北海道」はそのまま維持
2. 「東京」「京都」は「都」「府」を削除
3. その他の都道府県は「県」を削除
4. 「全国」「地方」接尾辞はそのまま維持

**Implementation**: `normalize_region()` 関数（`update_gyousei_kuiki.py` から流用）

### Format Deduplication

同一年度・地域に複数の配布形式が存在する場合の優先順位:

1. **SHP** (ファイル名が `.zip` で終わり、`_GML` を含まない)
2. **GML** (ファイル名が `_GML.zip` で終わる)

**Implementation**: `deduplicate_by_format()` 関数（`update_gyousei_kuiki.py` から流用）

**Note**: 現時点（2023 年度版）では P29 は GML のみ提供。将来的に SHP が追加される可能性に備える。

## Data Flow

```
HTML テーブル（Web ページ）
  ↓ extract_table_rows()
[
  {"region_raw": "北海道", "year_display": "2023年（令和5年）", "filename": "P29-23_01_GML.zip"},
  {"region_raw": "青森県", "year_display": "2023年（令和5年）", "filename": "P29-23_02_GML.zip"},
  ...
]
  ↓ normalize_year() / normalize_region()
[
  {"region": "北海道", "year": "2023年", "filename": "P29-23_01_GML.zip"},
  {"region": "青森", "year": "2023年", "filename": "P29-23_02_GML.zip"},
  ...
]
  ↓ deduplicate_by_format()
[
  {"region": "北海道", "year": "2023年", "filename": "P29-23_01_GML.zip"},
  {"region": "青森", "year": "2023年", "filename": "P29-23_02_GML.zip"},
  ...
]
  ↓ group by year → region
{
  "2023年": {
    "北海道": "P29-23_01_GML.zip",
    "青森": "P29-23_02_GML.zip",
    ...
  }
}
  ↓ json.dump()
gakkou.json (UTF-8)
```

## URL Generation

### Download URL Format

```
https://nlftp.mlit.go.jp/ksj/gml/data/P29/P29-{YY}/{FILENAME}
```

**Components**:

- Base: `https://nlftp.mlit.go.jp/ksj/gml/data/`
- Data ID: `P29`
- Directory: `P29-{YY}` (2 桁年をファイル名から抽出)
- Filename: テーブル上のファイル名をそのまま使用

### Example

**Input**:

- Year: `2023年`
- Region: `北海道`
- Filename: `P29-23_01_GML.zip`

**Output**:

```
https://nlftp.mlit.go.jp/ksj/gml/data/P29/P29-23/P29-23_01_GML.zip
```

### Directory Year Extraction Strategy

P29 は A33 と同じ戦略を使用:

```python
def _get_dir_year_from_filename_yy(filename: str) -> str:
    """ファイル名から2桁年を抽出してディレクトリ名を生成

    例: P29-23_01_GML.zip → P29-23
    """
    data_id = filename.split('-')[0]  # "P29"
    yy_part = filename.split('-')[1].split('_')[0]  # "23"
    return f"{data_id}-{yy_part}"
```

**Mapping in `data_loader.py`**:

```python
_DIR_YEAR_STRATEGIES = {
    "A33": _get_dir_year_from_filename_yy,
    "P29": _get_dir_year_from_filename_yy,  # NEW
    "N03": _get_dir_year_from_input_yyyy,
}
```

## Entities

### DataCollection (既存)

| Field         | Type | Description                     |
| ------------- | ---- | ------------------------------- |
| collection_id | str  | コレクション ID（例: `gakkou`） |
| display_name  | str  | 表示名（例: `学校`）            |
| data          | dict | 年度ごとの地域別ファイル情報    |

### YearlyData (既存)

| Field   | Type | Description                     |
| ------- | ---- | ------------------------------- |
| year    | str  | 年度（例: `2023年`）            |
| regions | dict | 地域名 → ファイル名のマッピング |

### RegionalFile (既存)

| Field    | Type | Description                               |
| -------- | ---- | ----------------------------------------- |
| region   | str  | 地域名（正規化済み、例: `北海道`）        |
| filename | str  | ZIP ファイル名（例: `P29-23_01_GML.zip`） |

## File Locations

| File       | Path                               | Description                      |
| ---------- | ---------------------------------- | -------------------------------- |
| Definition | `ksj/data_collections/gakkou.json` | コレクション定義（コミット同梱） |
| Generator  | `scripts/update_gakkou.py`         | 開発者向け生成ツール             |
| Tests      | `tests/test_update_gakkou.py`      | 生成ツールのテスト               |
| Fixture    | `tests/fixtures/p29_sample.html`   | テスト用 HTML サンプル           |

## State Management

学校データのコレクション定義は**静的ファイル**として管理され、実行時の状態変更はありません。

- 生成: `python scripts/update_gakkou.py` で上書き更新
- 読み込み: `ksj.data_loader.load_data_collections()` で JSON ファイルをロード
- 表示: `ksj.browser.KsjCollectionItem` でブラウザパネルに表示

## Validation Rules

### File Generation

- **必須フィールド**: `region_raw`, `year_display`, `filename` が全て揃っている行のみを処理
- **重複排除**: 同一年度・地域の重複は SHP 優先で解決
- **エンコーディング**: UTF-8 で保存
- **フォーマット**: JSON インデント 2 スペース

### Runtime Loading

- **ファイル存在確認**: `gakkou.json` が存在しない場合はエラーログを記録してスキップ
- **JSON パース**: 不正な JSON はエラーログを記録してスキップ
- **表示名登録**: `data_loader.get_data_collection_name("gakkou")` が `"学校"` を返す

## Consistency with Existing Data

学校データ（P29）は既存の行政区域データ（N03）および土砂災害警戒区域データ（A33）と以下の点で一貫性を保ちます:

1. **JSON 構造**: 年度 → 地域 → ファイル名の階層構造
2. **地域名キー**: 正規化規則の統一
3. **年度キー**: `YYYY年` 形式
4. **配布形式優先順位**: SHP > GML
5. **URL 生成戦略**: データ ID ごとの戦略パターン
