# Data Model: Zip 再帰探索ブラウズ

この機能は DB を持たないため、永続化モデルではなく「処理・UI に必要な概念モデル」を定義する。

## Entities

### DataCollectionCatalog

- 概要: `ksj/data_collections/*.json` から読み込むカタログ
- フィールド:
  - `collection_id`: コレクション ID（例: `dosyasaigai_keikai_kuiki`）
  - `years`: 年度の集合（例: `2024年`）
  - `prefectures`: 都道府県 →ZIP ファイル名のマップ

### RemoteZipRef

- 概要: リモート上の ZIP を参照するための情報
- フィールド:
  - `url`: ダウンロード URL（例: `https://nlftp.mlit.go.jp/ksj/gml/data/.../....zip`）
  - `display_name`: UI 表示用（都道府県名 + ZIP 名等）

### ZipNode

- 概要: ZIP 内の階層を表すノード
- 種別:
  - `folder`: ディレクトリ
  - `file`: ファイル
- 共通フィールド:
  - `path`: ZIP 内パス（POSIX 形式）
  - `name`: 表示名
- file の追加フィールド:
  - `extension`: `.shp` / `.geojson` など
  - `is_supported`: 対象拡張子か

### LayerSource

- 概要: QGIS へ追加するための入力
- フィールド:
  - `vsi_path`: `/vsizip//vsicurl/<url>/<path-in-zip>`
  - `layer_name`: レイヤ名（通常はファイル名）
  - `provider`: 既定は `ogr`

## Relationships

- DataCollectionCatalog → RemoteZipRef: 年度 × 都道府県の選択により RemoteZipRef が決まる
- RemoteZipRef → ZipNode: リモート ZIP を走査して ZipNode ツリーを生成
- ZipNode(file) → LayerSource: 対象拡張子のファイルノードから LayerSource を生成

## Validation Rules

- ZIP 走査結果は `.geojson` / `.shp` のみを「地理データ項目」として扱う
- `.shp` は関連ファイル不足の可能性があるため、追加失敗時はユーザーに理由を提示する
- 同名ファイルがある場合は、表示名で区別可能にする（例: パスを含める）

## State/Transitions

- ブラウザ展開:

  1. 都道府県ノード作成
  2. リモート ZIP を走査
  3. ZipNode ツリーを子要素として構築

- ファイルノードの操作:
  - ダブルクリック/DnD → LayerSource 作成 → QGIS へ追加（成功/失敗を返す）
