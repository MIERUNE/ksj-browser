# Contract: Update Tool (update_gakkou.py)

**Feature**: [spec.md](../spec.md) | **Date**: 2026-01-14

## Purpose

学校データ（P29）のコレクション定義ファイルを国土数値情報 Web サイトから自動生成・更新するツールの入出力契約を定義します。

## Command-Line Interface

### Synopsis

```bash
python scripts/update_gakkou.py [--url URL] [--output OUTPUT]
```

### Options

#### `--url URL` (optional)

**Description**: P29 データページの URL を指定

**Default**: `https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P29-2023.html`

**Example**:

```bash
python scripts/update_gakkou.py --url https://example.com/custom-p29.html
```

**Constraints**:

- MUST be a valid HTTP/HTTPS URL
- MUST be accessible without authentication

---

#### `--output OUTPUT` (optional)

**Description**: 出力 JSON ファイルのパスを指定

**Default**: `ksj/data_collections/gakkou.json` (repository root からの相対パス)

**Example**:

```bash
python scripts/update_gakkou.py --output /tmp/test_gakkou.json
```

**Constraints**:

- MUST be a writable file path
- Parent directory MUST exist or be creatable

## Input Contract

### HTML Table Structure

ツールは以下の HTML テーブル構造を期待します:

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
	</tbody>
</table>
```

### Expected Columns

| Index | Column Name  | Description        | Example             |
| ----- | ------------ | ------------------ | ------------------- |
| 0     | 地域         | 地域名（都道府県） | `北海道`, `青森県`  |
| 1     | 測地系       | 測地系（スキップ） | `世界測地系`        |
| 2     | 年           | 年度               | `2023年（令和5年）` |
| 3     | ファイル容量 | サイズ（スキップ） | `5.19MB`            |
| 4     | ファイル名   | ZIP ファイル名     | `P29-23_01_GML.zip` |

### Normalization Rules (Input → Output)

| Field      | Input Example       | Output Example      | Normalization      |
| ---------- | ------------------- | ------------------- | ------------------ |
| 地域       | `青森県`            | `青森`              | 都道府県接尾辞削除 |
| 年         | `2023年（令和5年）` | `2023年`            | 西暦抽出           |
| ファイル名 | `P29-23_01_GML.zip` | `P29-23_01_GML.zip` | そのまま           |

## Output Contract

### Success (Exit Code 0)

**Stdout**: 処理サマリー（オプショナル）

```
Fetched 47 rows from https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P29-2023.html
Generated ksj/data_collections/gakkou.json with 2 years and 47 regions
```

**File**: `gakkou.json` が生成または上書きされる

**Guarantees**:

- ✅ ファイルは valid JSON（UTF-8, インデント 2）
- ✅ 年度キーは降順ソート
- ✅ 地域キーは HTML 順序を維持
- ✅ 全てのエントリは非空文字列

### Failure: Network Error (Exit Code 1)

**Stderr**:

```
Error: Failed to fetch URL
Details: HTTPError 404: Not Found
```

**Conditions**:

- URL が存在しない（404）
- ネットワーク接続エラー
- タイムアウト

**File**: 既存ファイルは変更されない

---

### Failure: Parse Error (Exit Code 2)

**Stderr**:

```
Error: Failed to parse HTML table
Details: No table with class 'responsive-table' found
```

**Conditions**:

- 期待するテーブル構造が見つからない
- 必須カラム（地域、年、ファイル名）が欠落
- 有効な行が 0 件

**File**: 既存ファイルは変更されない

---

### Failure: Write Error (Exit Code 3)

**Stderr**:

```
Error: Failed to write output file
Details: PermissionError: [Errno 13] Permission denied: 'gakkou.json'
```

**Conditions**:

- 出力先ディレクトリが書き込み不可
- ディスク容量不足
- ファイルシステムエラー

**File**: 部分的に書き込まれたファイルが残る可能性あり（atomicity は保証されない）

## Behavior Specifications

### Deduplication Strategy

同一年度・地域に複数のファイル（SHP/GML）が存在する場合:

1. **SHP 優先**: ファイル名が `.zip` で終わり、`_GML` を含まない
2. **GML フォールバック**: ファイル名が `_GML.zip` で終わる

**Example**:

**Input** (hypothetical):

```
2023年, 北海道, P29-23_01.zip       # SHP
2023年, 北海道, P29-23_01_GML.zip   # GML
```

**Output**:

```json
{
	"2023年": {
		"北海道": "P29-23_01.zip"
	}
}
```

### Row Filtering

テーブル行は以下の条件で**スキップ**されます:

- ヘッダー行（`<th>` タグを含む）
- 必須フィールド（地域、年、ファイル名）のいずれかが空
- 地域名が正規化不可（例: 未知のフォーマット）

スキップされた行は警告ログに記録されます（オプショナル）。

### Idempotency

ツールは**べき等**です:

- 同じ入力（URL）に対して、何度実行しても同じ出力（JSON）を生成
- 既存ファイルは上書きされ、前回の内容は保持されない

## Dependencies

### Standard Library Only

- `argparse`: CLI 引数解析
- `json`: JSON 出力
- `html.parser.HTMLParser`: HTML パース
- `urllib.request`: HTTP リクエスト
- `pathlib`: ファイルパス操作
- `sys`: 終了コード
- `typing`: 型ヒント

**Rationale**: QGIS 3.28 同梱 Python に追加依存を持ち込まない

## Testing Contract

### Unit Tests

```python
def test_normalize_year():
    """年度正規化のテスト"""
    assert normalize_year("2023年（令和5年）") == "2023年"
    assert normalize_year("令和5年") == "2023年"

def test_normalize_region():
    """地域名正規化のテスト"""
    assert normalize_region("青森県") == "青森"
    assert normalize_region("北海道") == "北海道"
    assert normalize_region("東京都") == "東京"

def test_extract_table_rows(p29_sample_html):
    """HTML パースのテスト"""
    rows = extract_table_rows(p29_sample_html)
    assert len(rows) > 0
    assert "region_raw" in rows[0]
    assert "year_display" in rows[0]
    assert "filename" in rows[0]
```

### Integration Tests (Optional)

```python
@pytest.mark.integration
def test_fetch_real_p29_page():
    """実際の P29 ページからデータ取得（ネットワーク必要）"""
    url = "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P29-2023.html"
    # ... actual fetch and parse
```

### Fixture

`tests/fixtures/p29_sample.html`: P29 テーブルの HTML サンプル（数行分）

## Compatibility

### Existing Tools

- `update_gyousei_kuiki.py`: N03 データ用（同じ設計パターン）
- `update_dosyasaigai_keikai_kuiki.py`: A33 データ用（同じ設計パターン）

### Design Consistency

| Aspect        | update_gakkou.py                         | update_gyousei_kuiki.py |
| ------------- | ---------------------------------------- | ----------------------- |
| CLI           | `--url`, `--output`                      | 同じ                    |
| Exit Codes    | 0/1/2/3                                  | 同じ                    |
| HTML Parser   | `HTMLParser`                             | 同じ                    |
| Normalization | `normalize_year()`, `normalize_region()` | 同じロジック            |
| Deduplication | SHP > GML                                | 同じ                    |
| Output Format | UTF-8, indent=2                          | 同じ                    |

## Security Considerations

### Input Validation

- URL は `http://` または `https://` のみ許可
- 出力パスはディレクトリトラバーサル攻撃を防ぐ（`Path.resolve()` 使用）

### Network Access

- User-Agent ヘッダーを設定（`Python-urllib/3.9`）
- タイムアウトを設定（デフォルト: 30 秒）
- HTTPS 証明書検証を有効化

### File System

- 既存ファイルの上書きは**警告なし**で実行
- ファイルパーミッションは環境デフォルトに従う

## Usage Examples

### デフォルト実行

```bash
python scripts/update_gakkou.py
# → ksj/data_collections/gakkou.json を生成
```

### カスタム URL

```bash
python scripts/update_gakkou.py --url https://example.com/p29-test.html
```

### カスタム出力先

```bash
python scripts/update_gakkou.py --output /tmp/test.json
```

### 組み合わせ

```bash
python scripts/update_gakkou.py \
  --url https://example.com/p29.html \
  --output /tmp/gakkou_test.json
```

### エラーハンドリング

```bash
python scripts/update_gakkou.py --url https://invalid-url.com
# Exit code: 1
# Stderr: Error: Failed to fetch URL

python scripts/update_gakkou.py --output /root/gakkou.json
# Exit code: 3 (if permission denied)
# Stderr: Error: Failed to write output file
```
