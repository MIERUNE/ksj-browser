# Contract: Remote ZIP 走査

このドキュメントは、リモート ZIP を走査して ZIP 内の対象ファイル（`.shp` / `.geojson`）を列挙するための「内部契約（インターフェース）」を定義する。

## Inputs

- `collection_id`: 例 `dosyasaigai_keikai_kuiki`
- `year`: 例 `2024年`
- `prefecture`: 例 `北海道`
- `filename`: 例 `A33-24_01_SHP.zip`

## URL

- `download_url = build_download_url(collection_id, year, filename)`
- 期待する形式: `https://nlftp.mlit.go.jp/ksj/gml/data/<DATA_ID>/<DATA_ID>-<YY>/<FILENAME>`

## VSI Path

- `vsi_zip_root = /vsizip//vsicurl/<download_url>`
- `vsi_file_path = /vsizip//vsicurl/<download_url>/<path-in-zip>`

## Public API (ksj/zip_scanner.py)

この契約を実装する公開 API（関数名/戻り値/例外）は次に一致すること。

- `vsi_zip_root(download_url: str) -> str`
- `list_entries(vsi_zip_root: str) -> list[str]`
- `list_entries_recursive(vsi_zip_root: str) -> list[str]`
- `filter_supported(zip_paths: list[str]) -> list[str]`
- `build_tree(zip_paths: list[str]) -> ZipNode`

### ZipNode

- `ZipNode` は ZIP 内のフォルダ/ファイル階層を表現する（詳細は data-model.md を参照）
- `build_tree()` は「ファイルパス一覧」からフォルダノードを自動生成してよい

### Errors

- 取得失敗は例外で伝播する（空リストで握りつぶさない）
- 例外はユーザー向けに表示可能なメッセージ（`user_message`）を持つこと
  - 例: `ZipScanError(user_message: str, debug_details: str | None = None)`

## ZIP Listing

- `list_entries(vsi_zip_root) -> list[str]`

  - 戻り値: `vsi_zip_root` 直下のエントリ名（フォルダ名/ファイル名）
  - 失敗時: 例外または空を返すのではなく、「取得失敗」を上位に伝播できる形（例外）を優先
  - ログ出力: `QgsMessageLog` を使用して entries の内容をログ出力（テスト環境では無視）

- `list_entries_recursive(vsi_zip_root) -> list[str]`
  - 戻り値: ZIP 内のファイルパス（POSIX 形式）一覧
  - ルール:
    - フォルダ階層は `/` 区切り
    - 返すのはファイルのみとする（フォルダノードは `build_tree()` が生成する）
  - フォルダ判定: `gdal.VSIStatL()` を使用し、`stat.IsDirectory()` で判定
    - 注意: `gdal.ReadDir()` はフォルダ名に末尾の `/` を付けないため、文字列での判定は不可

### Path normalization

- 返すパスは ZIP ルートからの相対パス（先頭 `/` なし）
- 区切りは常に `/`（OS 依存の区切りは混入させない）
- `.` / `..` を含めない

## Filtering

- `filter_supported(entries) -> list[str]`
  - 対象: 拡張子 `.shp` または `.geojson`（大小文字は要件に応じて扱う）

## Error handling

- ネットワーク障害（未接続/403/404/タイムアウト）時は、ユーザーが理解できるエラーとして表示できる情報を上位へ返す
- ZIP が破損している場合も同様

## Test data source

- 受入テスト用の入力（`collection_id/year/prefecture/filename`）は `ksj/data_collections/*.json` を唯一のソースとする
