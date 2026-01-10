# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

これは国土数値情報（KSJ）をQGISで利用するためのQGISプラグイン開発プロジェクトです。QGISのカスタムデータプロバイダとして実装され、KSJデータをQGISに追加する機能を提供します。

## Architecture

### Core Components

- **KsjDataItemProvider** (`ksj/browser.py`): QGISブラウザパネルにKSJデータを表示するプロバイダ
- **KsjRootItem, KsjCollectionItem, KsjYearItem, KsjDataItem** (`ksj/browser.py`): ブラウザ階層構造を実現するアイテム群
- **data_loader** (`ksj/data_loader.py`): JSONデータコレクションの読み込みとURL構築
- **Plugin** (`plugin.py`): QGISプラグインのエントリポイント。ブラウザアイテムプロバイダを登録

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

1. `ksj/data_collections/`内のJSONファイルがデータ定義を保持
2. `data_loader`がJSONを読み込み、ダウンロードURLを構築
3. `browser.py`のアイテム群がブラウザに階層表示（データコレクション > 年度 > 都道府県）
4. ダブルクリック時にGDAL VFS（`/vsizip//vsicurl/`）を使用してogrプロバイダ経由でレイヤーを追加

## Development Setup

### 仮想環境の作成

QGISのPythonインタプリタを使用した仮想環境が必要です：

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
# テストスイート実行
python test_suite.py
```

プラグインのテストはQGIS環境が必要です。CI/CDでは以下のQGISバージョンでテストされます：
- QGIS 3.28
- QGIS 3.34

## Code Style Guidelines

### Import Style

**相対インポートを使用すること**: Plugin Reloaderでの変更反映を確実にするため、絶対インポートは避けてください。

```python
# NG
from child import Child

# OK
from .child import Child
```

### Qt UIファイルの型定義

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

- **lint.yaml**: Ruffによるコードチェックとフォーマット確認（PR時）
- **test.yaml**: Dockerコンテナ内でQGIS環境を使用したプラグインテスト（PR時）
- **release.yaml**: リリースビルド

## Adding New Data Collections

新しいKSJデータコレクションを追加する手順：

1. `ksj/data_collections/`に新しいJSONファイルを作成
   - ファイル名がコレクションIDになります（例: `suigai_shinsuisouteiku.json`）
   - フォーマット：`{"<年度>": {"<都道府県名>": "<ZIPファイル名>", ...}, ...}`

2. `ksj/data_loader.py`の`get_data_collection_name()`に表示名を追加
   ```python
   name_mapping = {
       "dosyasaigai_keikai_kuiki": "土砂災害警戒区域",
       "suigai_shinsuisouteiku": "浸水想定区域",  # 新規追加
   }
   ```

3. ファイル構造が異なる場合は`get_shapefile_path_in_zip()`を調整

4. QGISを再起動してブラウザに表示されることを確認

## VSCode Settings

プロジェクトには以下の設定が含まれています：
- 保存時の自動フォーマット
- インポートの自動整理
- Ruffをデフォルトフォーマッタとして使用
- Python基本型チェック有効化
