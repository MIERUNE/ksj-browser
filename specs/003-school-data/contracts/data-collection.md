# Contract: Data Collection Definition (gakkou.json)

**Feature**: [spec.md](../spec.md) | **Date**: 2026-01-14

## Purpose

学校データ（P29）のコレクション定義ファイル `gakkou.json` の構造と制約を定義します。このファイルは生成ツール（`update_gakkou.py`）によって作成され、QGIS プラグイン（`ksj.data_loader`）によって読み込まれます。

## Schema

```json
{
	"<YEAR>": {
		"<REGION>": "<FILENAME>"
	}
}
```

## Field Specifications

### `<YEAR>` (string, required)

**Format**: `YYYY年` (4 桁西暦 + 「年」)

**Examples**: `2023年`, `2021年`, `2019年`

**Constraints**:

- MUST be in `YYYY年` format
- MUST be a valid year (≥1900 and ≤ current year + 10)
- Keys MUST be sorted in descending order (新しい年度が先)

**Validation**:

```python
import re
assert re.match(r'^\d{4}年$', year_key)
assert 1900 <= int(year_key[:-1]) <= 2036
```

---

### `<REGION>` (string, required)

**Format**: 正規化された地域名（都道府県名から接尾辞を削除）

**Examples**: `北海道`, `青森`, `東京`, `京都`, `全国`, `東北地方`

**Constraints**:

- MUST NOT include prefixes like `県`, `都`, `府` (except `北海道`)
- MUST be consistent with existing collections (`gyousei_kuiki`, `dosyasaigai_keikai_kuiki`)
- Keys SHOULD be ordered as they appear in the source HTML table

**Normalization Rules**:
| Input | Output |
|-------|--------|
| `北海道` | `北海道` |
| `青森県` | `青森` |
| `東京都` | `東京` |
| `京都府` | `京都` |
| `全国` | `全国` |
| `東北地方` | `東北地方` |

---

### `<FILENAME>` (string, required)

**Format**: `P29-{YY}_{REGION_CODE}_{FORMAT}.zip` または `P29-{YY}_{FORMAT}.zip` (全国)

**Examples**: `P29-23_01_GML.zip`, `P29-23_GML.zip`, `P29-21_02.zip`

**Constraints**:

- MUST start with `P29-`
- MUST end with `.zip`
- MUST include year indicator (2 digits after `P29-`)
- MAY include format suffix (`_GML` for GML, none for SHP)

**Validation**:

```python
import re
assert re.match(r'^P29-\d{2}(_\d{2})?(_GML)?\.zip$', filename)
```

## Complete Example

```json
{
	"2023年": {
		"全国": "P29-23_GML.zip",
		"北海道": "P29-23_01_GML.zip",
		"東北地方": "P29-23_52_GML.zip",
		"青森": "P29-23_02_GML.zip",
		"岩手": "P29-23_03_GML.zip",
		"宮城": "P29-23_04_GML.zip",
		"秋田": "P29-23_05_GML.zip",
		"山形": "P29-23_06_GML.zip",
		"福島": "P29-23_07_GML.zip"
	},
	"2021年": {
		"全国": "P29-21_GML.zip",
		"北海道": "P29-21_01_GML.zip",
		"青森": "P29-21_02_GML.zip"
	}
}
```

## Producer Contract (update_gakkou.py)

### Responsibilities

1. **Fetch HTML**: 指定された URL（デフォルト: P29 の公式ページ）から HTML を取得
2. **Parse Table**: テーブル行を抽出し、`region_raw`, `year_display`, `filename` を取得
3. **Normalize**: 年度と地域名を正規化
4. **Deduplicate**: 同一年度・地域の重複は SHP 優先で解決
5. **Group**: 年度 → 地域 → ファイル名の階層構造に変換
6. **Write**: `ksj/data_collections/gakkou.json` に UTF-8, インデント 2 で出力

### Error Handling

| Error Type    | Exit Code | Behavior                                             |
| ------------- | --------- | ---------------------------------------------------- |
| Network error | 1         | URL 取得失敗時、エラーメッセージを stderr に出力     |
| Parse error   | 2         | テーブル未検出時、エラーメッセージを stderr に出力   |
| Write error   | 3         | ファイル保存失敗時、エラーメッセージを stderr に出力 |

### Output Guarantees

- ✅ ファイルは UTF-8 エンコーディング
- ✅ JSON は valid で、インデント 2 スペース
- ✅ 年度キーは降順（新 → 旧）
- ✅ 地域キーは HTML テーブル順序を維持
- ✅ 全てのフィールドは非空文字列

## Consumer Contract (ksj.data_loader, ksj.browser)

### Responsibilities

1. **Load**: `load_data_collections()` で `gakkou.json` を読み込む
2. **Register**: `get_data_collection_name("gakkou")` が `"学校"` を返す
3. **Display**: ブラウザパネルで年度 → 地域のツリー構造を表示
4. **Generate URL**: `build_download_url("P29", year, filename)` で正しい URL を生成

### Assumptions

- ファイルが存在し、valid な JSON である
- 全てのキーと値は非空文字列である
- 年度キーは `YYYY年` 形式である
- 地域キーは正規化済みである
- ファイル名は `P29-` で始まる

### Error Handling

| Error Type     | Behavior                               |
| -------------- | -------------------------------------- |
| File not found | エラーログ記録、コレクションをスキップ |
| Invalid JSON   | エラーログ記録、コレクションをスキップ |
| Missing keys   | エラーログ記録、該当エントリをスキップ |

## Versioning

### Current Version: 1.0

- Initial schema for P29 (学校) data
- Compatible with existing N03 (行政区域) and A33 (土砂災害警戒区域) schemas

### Future Considerations

- 複数年度の一括管理
- メタデータの追加（更新日時、データソース URL など）
- 配布形式の明示（SHP/GML フラグ）

## Testing

### Producer Tests

```python
def test_gakkou_json_schema():
    """生成された JSON がスキーマに準拠しているか"""
    with open("ksj/data_collections/gakkou.json") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    for year, regions in data.items():
        assert re.match(r'^\d{4}年$', year)
        assert isinstance(regions, dict)
        for region, filename in regions.items():
            assert isinstance(region, str) and region
            assert isinstance(filename, str) and filename.startswith("P29-")
```

### Consumer Tests

```python
def test_load_gakkou_collection():
    """gakkou.json が正しく読み込まれるか"""
    collections = data_loader.load_data_collections()
    assert "gakkou" in collections
    assert data_loader.get_data_collection_name("gakkou") == "学校"

def test_build_gakkou_url():
    """P29 の URL が正しく生成されるか"""
    url = data_loader.build_download_url("P29", "2023年", "P29-23_01_GML.zip")
    assert url == "https://nlftp.mlit.go.jp/ksj/gml/data/P29/P29-23/P29-23_01_GML.zip"
```
