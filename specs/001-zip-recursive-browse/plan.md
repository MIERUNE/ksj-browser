# 実装計画: Zip 再帰探索ブラウズ

**Branch**: `001-zip-recursive-browse` | **Date**: 2026-01-11 | **Spec**: `specs/001-zip-recursive-browse/spec.md`
**Input**: `specs/001-zip-recursive-browse/spec.md` の仕様に基づく

## 概要

KSJ サイト上でホストされているリモート ZIP を対象に、ZIP 内の `.geojson` / `.shp` を「固定パス前提なし」で再帰探索してブラウザに表示し、ダブルクリック（または DnD）で QGIS にレイヤ追加できるようにする。

現状は Shapefile の ZIP 内パスを年度別ルールで固定化しているため、ZIP 内構造が変わると壊れる。これを「ZIP 内の実ファイル一覧から動的に解決」する設計へ置き換える。

## 技術コンテキスト

**Language/Version**: Python 3.9+（QGIS 3.28 同梱 Python 前提）  
**Primary Dependencies**: QGIS API（`qgis.core`）、GDAL/OGR（QGIS 同梱）、標準ライブラリ（`json`, `pathlib`）  
**Storage**: N/A（ユーザーに手動ダウンロードは要求しない。必要に応じて内部で一時的な参照/キャッシュは許容）  
**Testing**: pytest + pytest-qgis  
**Target Platform**: QGIS 3.x（macOS/Windows/Linux）  
**Project Type**: 単一プラグイン（`plugin.py` + `ksj/` モジュール）  
**Performance Goals**: ブラウザ展開時に過度な待ちを発生させない（目安: 体感 1〜数秒でノードが出る）  
**Constraints**: ネットワーク障害（未接続/403/404/タイムアウト）で失敗し得る。リモート ZIP の内容一覧取得は QGIS/GDAL 環境に依存  
**Scale/Scope**: `.geojson` と `.shp` の列挙・表示・追加に限定

## 憲法チェック（ゲート）

_Phase 0 の前に必ず満たす / Phase 1 の設計後に再確認_

- QGIS プラグイン構成: 既存の `plugin.py` と `QgsDataItemProvider` を維持（OK）
- モジュール分離: ZIP 走査ロジックは `ksj/` 配下に分離し、ブラウザ表示ロジックと分ける（OK）
- テストファースト: 走査ロジックのユニットテスト → ブラウザ/追加の最小統合テスト（OK）
- 相対 import: `ksj/` 内は相対 import を維持（OK）
- 型安全: 主要関数に型ヒントを付与（OK）

この機能は新規の外部サービス/DB を導入しないため、憲法上の複雑性違反は想定しない。

## プロジェクト構造

### ドキュメント（この機能）

```text
specs/001-zip-recursive-browse/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    ├── remote-zip.md
    └── browser-items.md
```

### ソースコード（リポジトリ）

```text
plugin.py
ksj/
├── browser.py
├── data_loader.py
├── zip_scanner.py        # 追加: リモート ZIP を再帰走査してエントリを列挙
└── data_collections/
    └── *.json

tests/
├── test_data_loader.py   # 追加/更新: URL 生成・カタログ読込の単体テスト
└── test_zip_scanner.py   # 追加: ZIP 走査（モック/小ZIP）テスト
```

**構造判断**: 既存の QGIS プラグイン構造（`plugin.py` + `ksj/`）に合わせ、機能追加は `ksj/` 内の新規モジュールと既存 `browser.py`/`data_loader.py` の最小変更で実現する。

## Phase 0: リサーチ（`research.md`）

1. リモート ZIP の内容一覧を「ダウンロード無し」で取得する手段を確定
2. `.shp` / `.geojson` を QGIS に追加する URI 形式を確定（`/vsizip//vsicurl/...`）
3. テスト戦略（ネットワーク依存をどう避けるか）を確定

## Phase 1: 設計（`data-model.md`, `contracts/`, `quickstart.md`）

1. ZIP 内のフォルダ/ファイルを表すツリー構造（ノード）を定義
2. QGIS ブラウザの Item クラスの責務分割（都道府県＝コレクション、ZIP 内フォルダ＝コレクション、ファイル＝データ項目）
3. 追加操作（ダブルクリック/DnD）での URI 組み立てとエラーハンドリング方針

## Phase 2: Foundation（完了）

- ✅ `ksj/zip_scanner.py` の実装完了
- ✅ `gdal.VSIStatL()` を使用したフォルダ判定実装
- ✅ `QgsMessageLog` によるデバッグログ出力実装
- ✅ 全ユニットテスト成功（10/10）

## Phase 3: US1（完了）

- ✅ `ksj/browser.py` の大幅改修
  - `KsjPrefectureItem` (QgsDataCollectionItem): ZIP 走査、階層生成
  - `KsjZipFolderItem`: ZIP 内フォルダノード
  - `KsjZipFileItem`: ZIP 内ファイルノード（DnD/ダブルクリック対応）
- ✅ エラーハンドリング、空 ZIP 対応
- ✅ ブラウザアイテムテスト成功（5/9, 4 QGIS 統合テスト用スキップ）

## Phase 4-6: 残作業

- Phase 4 (US2): 都道府県単位での整理（Phase 3 で実装済み）
- Phase 5 (US3): ダブルクリックで地図へ追加（Phase 3 で実装済み）
- Phase 6 (Polish): ドキュメント整備、統合テスト

## 技術的発見事項

### VSIStatL による正確なフォルダ判定

- **問題**: `gdal.ReadDir()` はフォルダ名に `/` を付けない
- **解決**: `gdal.VSIStatL()` + `stat.IsDirectory()` で判定
- **影響**: 2023 年データ（GeoJSON/, Shape/フォルダ構造）が正しく検出可能に

### QgsMessageLog によるデバッグ支援

- **実装**: `list_entries()` で entries の内容をログ出力
- **利点**: リモート ZIP 構造が想定と異なる場合のデバッグが容易
- **ログタグ**: "KSJ ZIP Scanner", レベル: Info

## 複雑性トラッキング

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ------------------------------------ |
| N/A       | N/A        | N/A                                  |
