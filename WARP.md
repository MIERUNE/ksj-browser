# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

これは国土数値情報（KSJ）を QGIS で利用するための QGIS プラグイン開発プロジェクトです。QGIS のカスタムデータプロバイダとして実装され、KSJ データを QGIS に追加する機能を提供します。

## Architecture

### Core Components

- **KsjDataItemProvider** (`ksj/browser.py`): QGIS ブラウザパネルに KSJ データを表示するプロバイダ
- **KsjRootItem, KsjCollectionItem, KsjYearItem, KsjDataItem** (`ksj/browser.py`): ブラウザ階層構造を実現するアイテム群
- **data_loader** (`ksj/data_loader.py`): JSON データコレクションの読み込みと URL 構築
- **Plugin** (`plugin.py`): QGIS プラグインのエントリポイント。ブラウザアイテムプロバイダを登録

### Directory Structure

```
ksj-provider/
├── ksj/
│   ├── __init__.py
│   ├── browser.py              # ブラウザパネル用アイテム実装
│   ├── data_loader.py          # JSONデータ読み込み・URL構築
│   └── data_collections/       # データ定義ファイル（JSON）
│       └── dosyasaigai_keikai_kuiki.json
├── ui/                         # UIモジュール（将来の拡張用）
├── tests/                      # ユニットテスト
├── plugin.py                   # プラグインエントリポイント
├── __init__.py                 # プラグイン初期化
├── metadata.txt                # プラグインメタデータ
└── pyproject.toml              # プロジェクト設定
```

### Data Flow

1. `ksj/data_collections/`内の JSON ファイルがデータ定義を保持
2. `data_loader`が JSON を読み込み、ダウンロード URL を構築
3. `browser.py`のアイテム群がブラウザに階層表示（データコレクション > 年度 > 都道府県）
4. ダブルクリック時に GDAL VFS（`/vsizip//vsicurl/`）を使用して ogr プロバイダ経由でレイヤーを追加

## Development Setup

### 仮想環境の作成

QGIS の Python インタプリタを使用した仮想環境が必要です：

```bash
# macOS
uv venv --python /Applications/QGIS.app/Contents/MacOS/bin/python3 --system-site-packages

# Windows
uv venv --python "C:\Program Files\QGIS 3.28.2\apps\Python39\python.exe" --system-site-packages
```

### 依存関係のインストール

```bash
uv sync
```

## Common Commands

### Linting and Formatting

```bash
# コードチェック
uv run ruff check .

# フォーマットチェック
uv run ruff format . --check

# 自動修正
uv run ruff check --fix .

# フォーマット適用
uv run ruff format .
```

### Testing

```bash
# QGIS環境変数を設定してからテスト実行 (macOS)
source setup_qgis_env.sh
uv run pytest

# または環境変数を一度に設定して実行
export DYLD_LIBRARY_PATH=/Applications/QGIS.app/Contents/MacOS/lib:$DYLD_LIBRARY_PATH
export PROJ_LIB=/Applications/QGIS.app/Contents/Resources/proj
export GDAL_DATA=/Applications/QGIS.app/Contents/Resources/gdal
uv run pytest -v

# 特定のテストのみ実行
uv run pytest tests/test_smoke.py -v
```

**重要**: pytest-qgis を使用する場合、QGIS の環境変数を pytest 起動**前**に設定する必要があります。
`setup_qgis_env.sh` をソースするか、上記のように export してから実行してください。

プラグインのテストは QGIS 環境が必要です。CI/CD では以下の QGIS バージョンでテストされます：

- QGIS 3.28
- QGIS 3.34

## Code Style Guidelines

### Import Style

**相対インポートを使用すること**: Plugin Reloader での変更反映を確実にするため、絶対インポートは避けてください。

```python
# NG
from child import Child

# OK
from .child import Child
```

### Qt UI ファイルの型定義

`uic.loadUi()`で生成されるインスタンスには型定義がないため、`typing.cast`を使用して型を明示的に定義します：

```python
from typing import cast
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLineEdit
from PyQt5 import uic

class DialogType:
    # UIファイルで定義されたウィジェットの型定義
    verticalLayout: QVBoxLayout
    lineEdit: QLineEdit

class Dialog(QDialog):
    def __init__(self):
        super().__init__()
        self.ui = cast(
            DialogType,
            uic.loadUi(os.path.join(os.path.dirname(__file__), "dialog.ui"), self),
        )
```

## Package Manager

このプロジェクトは`uv`をパッケージマネージャとして使用します。`pip`ではなく`uv`を使用してください。

## CI/CD

### GitHub Actions Workflows

- **lint.yaml**: Ruff によるコードチェックとフォーマット確認（PR 時）
- **test.yaml**: Docker コンテナ内で QGIS 環境を使用したプラグインテスト（PR 時）
- **release.yaml**: リリースビルド

## Adding New Data Collections

新しい KSJ データコレクションを追加する手順：

1. `ksj/data_collections/`に新しい JSON ファイルを作成

   - ファイル名がコレクション ID になります（例: `suigai_shinsuisouteiku.json`）
   - フォーマット：`{"<年度>": {"<都道府県名>": "<ZIPファイル名>", ...}, ...}`

2. `ksj/data_loader.py`の`get_data_collection_name()`に表示名を追加

   ```python
   name_mapping = {
       "dosyasaigai_keikai_kuiki": "土砂災害警戒区域",
       "suigai_shinsuisouteiku": "浸水想定区域",  # 新規追加
   }
   ```

3. ファイル構造が異なる場合は`get_shapefile_path_in_zip()`を調整

4. QGIS を再起動してブラウザに表示されることを確認

## VSCode Settings

プロジェクトには以下の設定が含まれています：

- 保存時の自動フォーマット
- インポートの自動整理
- Ruff をデフォルトフォーマッタとして使用
- Python 基本型チェック有効化
