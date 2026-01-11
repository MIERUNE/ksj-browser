# ksj-provider Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-01-11

## Active Technologies
- Python 3.9+（QGIS 3.28 同梱 Python 前提） + QGIS API（`qgis.core`）、GDAL/OGR（QGIS 同梱）、標準ライブラリ（`json`, `pathlib`） (001-zip-recursive-browse)
- N/A（ユーザーに手動ダウンロードは要求しない。必要に応じて内部で一時的な参照/キャッシュは許容） (001-zip-recursive-browse)
- Python 3.9+（QGIS 3.28同梱Pythonを想定） + QGIS 3.x (PyQt, qgis.core), GDAL/OGR（VSI: /vsizip//vsicurl） (002-admin-area-data)
- JSONファイル（データコレクション定義） (002-admin-area-data)

- (001-zip-recursive-browse)

## Project Structure

```text
src/
tests/
```

## Commands

# Add commands for 

## Code Style

: Follow standard conventions

## Recent Changes
- 002-admin-area-data: Added Python 3.9+（QGIS 3.28同梱Pythonを想定） + QGIS 3.x (PyQt, qgis.core), GDAL/OGR（VSI: /vsizip//vsicurl）
- 001-zip-recursive-browse: Added Python 3.9+（QGIS 3.28 同梱 Python 前提） + QGIS API（`qgis.core`）、GDAL/OGR（QGIS 同梱）、標準ライブラリ（`json`, `pathlib`）

- 001-zip-recursive-browse: Added

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
