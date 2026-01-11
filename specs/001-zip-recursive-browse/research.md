# Research: Zip 再帰探索ブラウズ

## 前提

- 対象 ZIP はローカルに存在せず、KSJ サイト（https://nlftp.mlit.go.jp/ksj/gml/data）上のリモートZIPを対象とする
- 受入テストの ZIP セットは `ksj/data_collections` 配下の JSON に記載された ZIP 名を用いる

## Decision 1: リモート ZIP の内容一覧取得方法

- Decision: GDAL の VSI（仮想ファイルシステム）を利用して、`/vsizip//vsicurl/<URL>` を `gdal.ReadDir()`（必要なら再帰）で列挙する
- Rationale:
  - 既存実装が `/vsizip//vsicurl` を使ってリモート ZIP 内の Shapefile を直接開けている（QGIS/GDAL 同梱の仕組み）
  - Python 標準の `zipfile` 方式だと「ZIP を全量ダウンロードする」か「Range 対応の複雑な実装」が必要になり、プラグインの依存と実装コストが増える
  - QGIS 同梱 GDAL の能力に寄せることで、追加の外部依存を増やさずに済む
- Alternatives considered:
  - `requests` 等で ZIP をダウンロード → `zipfile` で列挙（実装は単純だが通信量/待ち時間が増え、手元の一時ファイル管理も必要）
  - HTTP Range で中央ディレクトリのみ取得して列挙（高速だが実装が難しく、保守コストが高い）

## Decision 2: ブラウザツリーの表現

- Decision: 都道府県ノードは `QgsDataCollectionItem`（フォルダ/コレクション）として扱い、配下に ZIP 内のフォルダノード（コレクション）とファイルノード（データ項目）をぶら下げる
- Rationale:
  - 仕様（都道府県はコレクション扱い）に合致
  - ZIP 内階層を自然に表現でき、同名ファイルの識別にも有利（表示にパスを含められる）
- Alternatives considered:
  - これまで通り都道府県を単一の `QgsDataItem` にして直接レイヤ追加（シンプルだが、複数ファイル/複数階層に対応できない）

## Decision 3: レイヤ追加の URI

- Decision: `.shp` / `.geojson` ともに `uri = /vsizip//vsicurl/<URL>/<path-in-zip>` を使い、QGIS 側では OGR プロバイダで読み込む
- Rationale:
  - 既存の `.shp` 追加実装と整合し、拡張子の追加が最小変更で済む
- Alternatives considered:
  - `.geojson` だけ別プロバイダを使う（整合性が悪く、検証範囲が増える）

## Decision 4: テスト戦略（ネットワーク依存の扱い）

- Decision: デフォルトのテストはネットワークに依存しない（モック/小さなローカル ZIP）ユニットテストを中心にし、KSJ サイトへの実アクセスは任意の統合テストとして切り分ける
- Rationale:
  - CI/開発環境でネットワーク状態により不安定になるのを避ける
  - 仕様上の「テスト ZIP セット」は、JSON の値（ZIP 名/年度/都道府県）を入力に使い、リモート一覧取得はモックで再現可能
- Alternatives considered:
  - 常に KSJ サイトへアクセスして統合テスト（テストが不安定/遅くなる）

## Decision 5: フォルダとファイルの判定方法

- Decision: `gdal.ReadDir()` の返り値に対して `gdal.VSIStatL()` を使用し、`stat.IsDirectory()` でフォルダとファイルを正確に判定する
- Rationale:
  - 実装中に発見した事実: GDAL の `ReadDir()` はフォルダ名に `/` を付けずに返す（例: `GeoJSON`, `Shape`）
  - 当初の実装（`entry.endswith("/")` でのフォルダ判定）では、2023 年データなどフォルダ構造を持つ ZIP で「対象データなし」となる問題が発生
  - `VSIStatL()` を使うことで、GDAL VFS 上でのフォルダ/ファイル判定が確実に行える
- Implementation notes:
  - `gdal.VSIStatL(entry_vsi_path)` が `None` を返す場合は読み取りエラーとして扱う
  - テストでは `VSIStatL` のモックも必要（`MockStat` クラスで `IsDirectory()` を実装）
- Discovered issue:
  - **問題**: 2023 年の KSJ データ（`A33-23_02_GML.zip`）は `GeoJSON/`, `Shape/` というフォルダ構造を持つが、当初の実装では検出できなかった
  - **原因**: `gdal.ReadDir()` がフォルダ名に末尾の `/` を付けずに返すため、`entry.endswith("/")` では判定できない
  - **解決**: `gdal.VSIStatL()` + `stat.IsDirectory()` による正確な判定に変更

## Decision 6: デバッグとロギング

- Decision: ZIP 走査の際に `QgsMessageLog` を使用して entries の内容をログ出力する
- Rationale:
  - リモート ZIP の構造が想定と異なる場合のデバッグを容易にする
  - ユーザーが「対象データなし」となった理由を確認できるようにする
  - テスト環境では `QgsMessageLog` が `None` の場合はログをスキップ（テスト実行への影響なし）
- Implementation:
  - ログタグ: "KSJ ZIP Scanner"
  - ログレベル: `Qgis.Info`
  - 出力内容: VSI パスと entries の内容
