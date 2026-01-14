# Quickstart: 学校データのサポート追加

**Feature**: [spec.md](spec.md) | **Date**: 2026-01-14

## Overview

このクイックスタートガイドでは、学校データ（P29）のサポートを追加するための開発の流れを説明します。

## Prerequisites

- QGIS 3.28 以上がインストールされている
- Python 3.9+ (QGIS 同梱)
- `uv` パッケージマネージャー
- Git リポジトリのクローン

## Development Setup

### 1. 仮想環境の作成（初回のみ）

```bash
cd /path/to/ksj-provider
uv venv --python /Applications/QGIS.app/Contents/MacOS/bin/python3 --system-site-packages
```

**Note**: Windows の場合は QGIS インストールディレクトリの Python パスを指定してください。

### 2. 環境変数の設定（macOS のみ）

**重要**: macOS でテストを実行する際は、QGIS 環境変数を設定する必要があります。

```bash
# テスト実行時は常にこのコマンドを使用
source setup_qgis_env.sh && uv run python -m pytest -v
```

または、環境変数を設定してから個別に pytest を実行することもできます:

```bash
source setup_qgis_env.sh
.venv/bin/pytest tests/ -v
```

## Development Workflow

### Phase 1: データ更新ツールの作成

#### 1.1. テストファイルの作成

```bash
touch tests/test_update_gakkou.py
touch tests/fixtures/p29_sample.html
```

#### 1.2. HTML フィクスチャの準備

`tests/fixtures/p29_sample.html` に P29 ページのテーブル部分を数行分コピーします。

```html
<table class="mapjpn1 mb15 responsive-table">
	<tbody>
		<tr>
			<th>地域</th>
			<th>測地系</th>
			<th>年</th>
			<th>ファイル容量</th>
			<th>ファイル名</th>
		</tr>
		<tr>
			<td id="prefecture0">全国</td>
			<td class="txtCenter">世界測地系</td>
			<td class="txtCenter">2023年（令和5年）</td>
			<td class="txtCenter">1.13MB</td>
			<td class="txtCenter">P29-23_GML.zip</td>
		</tr>
		<tr>
			<td id="prefecture1">北海道</td>
			<td class="txtCenter">世界測地系</td>
			<td class="txtCenter">2023年（令和5年）</td>
			<td class="txtCenter">5.19MB</td>
			<td class="txtCenter">P29-23_01_GML.zip</td>
		</tr>
	</tbody>
</table>
```

#### 1.3. テストの作成（TDD）

`tests/test_update_gakkou.py`:

```python
import pytest
from pathlib import Path

# 相対インポートを使用
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.update_gakkou import (
    normalize_year,
    normalize_region,
    extract_table_rows,
)


def test_normalize_year():
    """年度正規化のテスト"""
    assert normalize_year("2023年（令和5年）") == "2023年"
    assert normalize_year("令和5年") == "2023年"


def test_normalize_region():
    """地域名正規化のテスト"""
    assert normalize_region("青森県") == "青森"
    assert normalize_region("北海道") == "北海道"
    assert normalize_region("東京都") == "東京"


def test_extract_table_rows():
    """HTML パースのテスト"""
    fixture_path = Path(__file__).parent / "fixtures" / "p29_sample.html"
    html = fixture_path.read_text(encoding="utf-8")

    rows = extract_table_rows(html)
    assert len(rows) >= 2
    assert rows[0]["region_raw"] == "全国"
    assert rows[0]["year_display"] == "2023年（令和5年）"
    assert rows[0]["filename"] == "P29-23_GML.zip"
```

#### 1.4. ツールの実装

`scripts/update_gakkou.py` を作成し、`update_gyousei_kuiki.py` を参考に実装します。

**主要な関数**:

- `normalize_year()`: 年度正規化（N03 から流用）
- `normalize_region()`: 地域名正規化（N03 から流用）
- `deduplicate_by_format()`: SHP/GML 重複解消（N03 から流用）
- `extract_table_rows()`: HTML テーブルパース
- `main()`: CLI エントリーポイント

#### 1.5. テスト実行

```bash
# macOS の場合: 環境変数を設定してから実行
source setup_qgis_env.sh && uv run python -m pytest tests/test_update_gakkou.py -v

# または仮想環境から直接実行
.venv/bin/pytest tests/test_update_gakkou.py -v
```

#### 1.6. ツールの実行

```bash
python scripts/update_gakkou.py
```

これにより `ksj/data_collections/gakkou.json` が生成されます。

---

### Phase 2: ブラウザパネル対応

#### 2.1. コレクション名の登録

`ksj/data_loader.py` の `get_data_collection_name()` に追加:

```python
def get_data_collection_name(collection_id: str) -> str:
    """コレクション ID から表示名を取得"""
    names = {
        "dosyasaigai_keikai_kuiki": "土砂災害警戒区域",
        "gyousei_kuiki": "行政区域",
        "gakkou": "学校",  # NEW
    }
    return names.get(collection_id, collection_id)
```

#### 2.2. URL 生成戦略の追加

`ksj/data_loader.py` の `_DIR_YEAR_STRATEGIES` に追加:

```python
_DIR_YEAR_STRATEGIES = {
    "A33": _get_dir_year_from_filename_yy,
    "N03": _get_dir_year_from_input_yyyy,
    "P29": _get_dir_year_from_filename_yy,  # NEW (A33 と同じ戦略)
}
```

#### 2.3. テストの追加

`tests/test_data_loader.py` に追加:

```python
def test_load_gakkou_collection():
    """gakkou.json が正しく読み込まれるか"""
    collections = data_loader.load_data_collections()
    assert "gakkou" in collections
    assert data_loader.get_data_collection_name("gakkou") == "学校"


def test_build_gakkou_url():
    """P29 の URL が正しく生成されるか"""
    url = data_loader.build_download_url("P29", "2023年", "P29-23_01_GML.zip")
    expected = "https://nlftp.mlit.go.jp/ksj/gml/data/P29/P29-23/P29-23_01_GML.zip"
    assert url == expected
```

#### 2.4. テスト実行

```bash
# macOS の場合: 環境変数を設定してから実行
source setup_qgis_env.sh && uv run python -m pytest tests/test_data_loader.py -v

# または仮想環境から直接実行
.venv/bin/pytest tests/test_data_loader.py -v
```

---

### Phase 3: 動作確認

#### 3.1. QGIS での手動確認

1. QGIS を起動
2. プラグインをリロード（Plugin Reloader 使用）
3. ブラウザパネルを開く
4. 「国土数値情報（KSJ）」→「学校」を展開
5. 任意の年度・地域を選択してダブルクリック
6. 地図キャンバスにデータが表示されることを確認

#### 3.2. 全テストの実行

```bash
# macOS の場合: 環境変数を設定してから実行
source setup_qgis_env.sh && uv run python -m pytest -v

# または仮想環境から直接実行
.venv/bin/pytest tests/ -v

# カバレッジ付きで実行
.venv/bin/pytest tests/ --cov=ksj --cov=scripts --cov-report=term-missing
```

---

## Common Tasks

### データ定義の更新

```bash
python scripts/update_gakkou.py
git add ksj/data_collections/gakkou.json
git commit -m "feat: Update gakkou.json with latest data"
```

### カスタム URL からの生成

```bash
python scripts/update_gakkou.py --url https://example.com/custom-p29.html
```

### テスト用 JSON の生成

```bash
python scripts/update_gakkou.py --output /tmp/test_gakkou.json
```

---

## Troubleshooting

### テストが失敗する

**Symptom**: `ModuleNotFoundError: No module named 'qgis'`

**Solution**:

```bash
# macOS の場合: 環境変数を設定してから実行
source setup_qgis_env.sh && uv run python -m pytest -v

# または仮想環境から直接実行
.venv/bin/pytest tests/ -v
```

---

### ツールがエラーで終了する

**Symptom**: Exit code 1 (Network error)

**Solution**:

- URL が正しいか確認
- ネットワーク接続を確認
- `--url` オプションでカスタム URL を試す

---

**Symptom**: Exit code 2 (Parse error)

**Solution**:

- HTML 構造が変更されていないか確認
- フィクスチャと実際のページを比較
- パーサーロジックを調整

---

### QGIS でデータが表示されない

**Symptom**: ブラウザパネルに「学校」が表示されない

**Solution**:

- `gakkou.json` が存在するか確認
- JSON が valid か確認（`cat ksj/data_collections/gakkou.json | jq .`）
- `get_data_collection_name("gakkou")` が登録されているか確認

---

**Symptom**: ダブルクリックしてもデータが読み込まれない

**Solution**:

- URL 生成が正しいか確認（テストで検証）
- ブラウザで URL を直接開いて ZIP ファイルが存在するか確認
- QGIS のエラーログを確認（`View` → `Panels` → `Log Messages`）

---

## Next Steps

1. ✅ データ更新ツールの作成とテスト
2. ✅ ブラウザパネル対応の実装とテスト
3. ✅ QGIS での手動確認
4. 📝 Pull Request の作成
5. 📝 ドキュメントの更新（README.md）

---

## Reference

- [Feature Spec](spec.md): 機能仕様
- [Implementation Plan](plan.md): 実装計画
- [Data Model](data-model.md): データモデル
- [Contracts](contracts/): 入出力契約
- [Research](research.md): 調査結果

---

## Quick Command Reference

```bash
# 仮想環境作成（初回のみ）
uv venv --python /Applications/QGIS.app/Contents/MacOS/bin/python3 --system-site-packages

# データ更新ツール実行
python scripts/update_gakkou.py

# テスト実行（macOS: 環境変数設定が必須）
source setup_qgis_env.sh && uv run python -m pytest tests/test_update_gakkou.py -v
source setup_qgis_env.sh && uv run python -m pytest tests/test_data_loader.py -v
source setup_qgis_env.sh && uv run python -m pytest -v  # 全テスト

# または仮想環境から直接実行
.venv/bin/pytest tests/ -v

# カバレッジ付きで実行
.venv/bin/pytest tests/ --cov=ksj --cov=scripts --cov-report=term-missing

# JSON 検証
cat ksj/data_collections/gakkou.json | jq .

# Git コミット
git add ksj/data_collections/gakkou.json scripts/update_gakkou.py tests/
git commit -m "feat: Add P29 (school) data support"
```
