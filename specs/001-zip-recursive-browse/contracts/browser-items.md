# Contract: QGIS ブラウザアイテム

このドキュメントは、QGIS ブラウザ上に表示するノードの種類と期待動作を定義する。

## Node types

### 1) コレクション（既存）

- 例: `国土数値情報（KSJ）` ルート、データ種別コレクション、年度
- クラス: `QgsDataCollectionItem`
- 動作:
  - 展開すると子を生成する
  - ネットワークアクセスは「必要な最小限」に留める

### 2) 都道府県ノード（変更対象）

- 目的: 都道府県をコレクションとして扱い、配下に ZIP 内階層を表示する
- クラス: `QgsDataCollectionItem`
- 入力:
  - `collection_id`, `year`, `prefecture`, `filename`
- 動作:
  - 展開時にリモート ZIP を走査して ZIP 内ツリーを生成
  - 取得失敗時は、クラッシュせずエラーメッセージを表示可能な状態で終了

### 3) ZIP 内フォルダノード

- クラス: `QgsDataCollectionItem`
- 動作:
  - 子フォルダ/子ファイルをぶら下げる

### 4) ZIP 内ファイルノード（地理データ項目）

- 対象: `.shp` / `.geojson`
- クラス: `QgsDataItem`（種別はファイル相当）
- DnD:
  - `mimeUris()` が `ogr` provider の URI を返す
- ダブルクリック:
  - `handleDoubleClick()` がレイヤを追加する（成功時 True/失敗時 False）
  - 失敗時はユーザーが理由を理解できる情報を提示する

## Layer add contract

- 入力: `vsi_file_path = /vsizip//vsicurl/<download_url>/<path-in-zip>`
- Provider: `ogr`
- レイヤ名: 既定はファイル名（必要ならパスを含めて識別）

## Test data source

- 受入テスト用の都道府県 ZIP は `ksj/data_collections/*.json` の値を用いる
