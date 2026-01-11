# Quickstart: Zip 再帰探索ブラウズ

## 前提

- QGIS 3.x（macOS の場合は /Applications/QGIS.app）
- Python 3.9+（QGIS 同梱の Python を使用）
- pytest-qgis を動かすために、QGIS ライブラリへの環境変数設定が必要（macOS）

## 開発環境セットアップ

### テスト実行環境（macOS）

```bash
# QGIS環境変数を設定
source setup_qgis_env.sh

# QGIS同梱のPythonでpytestを実行
/Applications/QGIS.app/Contents/MacOS/bin/python3 -m pytest tests/ -v
```

### setup_qgis_env.sh の内容

```bash
export DYLD_LIBRARY_PATH=/Applications/QGIS.app/Contents/MacOS/lib:$DYLD_LIBRARY_PATH
export PROJ_LIB=/Applications/QGIS.app/Contents/Resources/proj
export GDAL_DATA=/Applications/QGIS.app/Contents/Resources/gdal
echo "QGIS environment variables set for pytest-qgis"
```

## テスト実行

### ユニットテスト（推奨）

```bash
source setup_qgis_env.sh
/Applications/QGIS.app/Contents/MacOS/bin/python3 -m pytest tests/test_zip_scanner.py tests/test_data_loader.py tests/test_browser_items.py -v
```

**期待される結果**: 21 passed, 4 skipped

- `test_zip_scanner.py`: 10/10 ✅
- `test_data_loader.py`: 5/5 ✅
- `test_browser_items.py`: 5/9 ✅, 4 スキップ（QGIS 統合テスト）

### コード品質チェック

```bash
ruff check .
```

## 受入テスト用 ZIP の入力

- 受入テストの ZIP セットは `ksj/data_collections/*.json` に記載されている ZIP 名を使用する
- テスト例: `dosyasaigai_keikai_kuiki/2024年/北海道/A33-24_01_SHP.zip`
- ネットワーク依存の統合テストは環境により不安定になり得るため、デフォルトではモック中心のテスト構成

## 動作確認（QGIS）

1. **プラグインのインストール**:

   - QGIS プラグインマネージャーから「KSJ Provider」をインストール
   - または開発モードでリポジトリを直接参照

2. **ブラウザパネルでの確認**:

   - QGIS のブラウザパネルで「国土数値情報（KSJ）」配下にコレクションが表示される
   - コレクション → 年度 → 都道府県を展開

3. **ZIP 内階層の表示**:

   - 都道府県を展開すると、ZIP 内のフォルダ構造が表示される
   - 2023 年データ（例: `A33-23_02_GML.zip`）の場合:
     - `GeoJSON/` フォルダ → `A33-23_02Polygon.geojson`
     - `Shape/` フォルダ → `A33-23_02Polygon.shp`
   - 2024 年データ（例: `A33-24_01_SHP.zip`）の場合:
     - ZIP 直下に `A33-24_01Polygon.shp` など

4. **レイヤ追加**:

   - `.shp` / `.geojson` をダブルクリックするとレイヤが地図に追加される
   - ドラッグ&ドロップでも追加可能

5. **エラーハンドリング**:
   - ZIP 内に対象ファイルがない場合: "対象データなし" と表示
   - ZIP 読み込みエラー: ユーザー向けエラーメッセージが表示され、クラッシュしない

## デバッグ

### QgsMessageLog の確認

ZIP 走査時の entries の内容は QGIS のメッセージログに出力されます：

1. QGIS メニューから「表示」→「パネル」→「ログメッセージ」を開く
2. ログタグ「KSJ ZIP Scanner」を確認
3. 出力例: `list_entries: /vsizip//vsicurl/https://... -> ['GeoJSON', 'Shape', ...]`

### トラブルシューティング

**問題**: 2023 年データが「対象データなし」と表示される
**原因**: フォルダ構造（`GeoJSON/`, `Shape/`）が検出されていない
**解決**: `gdal.VSIStatL()` によるフォルダ判定が正しく機能しているか確認

- QgsMessageLog で entries の内容を確認
- `VSIStatL(path).IsDirectory()` が True を返すか確認

**問題**: テストで `ModuleNotFoundError: No module named 'qgis'`
**原因**: QGIS Python を使用していない
**解決**: `/Applications/QGIS.app/Contents/MacOS/bin/python3` を明示的に使用

## 技術的詳細

### ZIP 走査の実装

- **GDAL VSI**: `/vsizip//vsicurl/<URL>` でリモート ZIP を参照
- **フォルダ判定**: `gdal.VSIStatL()` + `stat.IsDirectory()` で正確に判定
  - 注意: `gdal.ReadDir()` はフォルダ名に `/` を付けないため、文字列判定は不可
- **再帰走査**: `list_entries_recursive()` が ZIP 内を再帰的に探索
- **対象ファイル**: `.shp` と `.geojson` のみをフィルタ

### ブラウザアイテム階層

```
KsjRootItem（ルート）
└── KsjCollectionItem（データコレクション）
    └── KsjYearItem（年度）
        └── KsjPrefectureItem（都道府県, QgsDataCollectionItem）
            ├── KsjZipFolderItem（ZIP内フォルダ）
            │   └── KsjZipFileItem（ファイル）
            └── KsjZipFileItem（ファイル）
```
