# Quickstart: 行政区域データ（gyousei_kuiki）

このドキュメントは、開発者が行政区域データ（N03）のサポートを更新・確認するための手順を提供します。

## 1. 定義ファイルの更新

**目的**: 国土数値情報の N03 ページから最新の一覧を取り込み、`gyousei_kuiki.json` を更新する

**実行方法**:

```bash
python scripts/update_gyousei_kuiki.py
```

**オプション**:

- `--url <URL>`: 取得元 URL をカスタマイズ（デフォルト: https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-v3_1.html）
- `--output <PATH>`: 出力先パスをカスタマイズ（デフォルト: ksj/data_collections/gyousei_kuiki.json）
- `--html-file <PATH>`: ローカル HTML ファイルから読み込む（ネットワーク不要）

**終了コード**:

- 0: 成功
- 1: ネットワークエラー
- 2: HTML パースエラー（テーブル未検出）
- 3: ファイル書き込みエラー

## 2. 生成物の確認

**確認項目**:

- `ksj/data_collections/gyousei_kuiki.json` が更新されている
- 年度キーが `YYYY年` 形式になっている（例: `2025年`）
- 地域キーが既存表記と一致している（例: `北海道`, `東京都`, `全国`）
- 各年度に適切なファイル名が設定されている（例: `N03-20250101_GML.zip`, `N03-20250101_01_GML.zip`）

**サンプル構造**:

```json
{
	"2025年": {
		"全国": "N03-20250101_GML.zip",
		"北海道": "N03-20250101_01_GML.zip",
		"青森県": "N03-20250101_02_GML.zip"
	},
	"2024年": {
		"全国": "N03-20240101_GML.zip",
		"北海道": "N03-20240101_01_GML.zip"
	}
}
```

## 3. QGIS での確認

**動作確認手順**:

1. QGIS を起動する
2. ブラウザパネルを開く（表示 → パネル → ブラウザ）
3. 「国土数値情報（KSJ）」ノードを展開する
4. 「行政区域」コレクションを選択する
5. 任意の年度（例: `2025年`）を展開する
6. 任意の地域（例: `北海道`）を展開する
7. ZIP 内のファイルツリーが表示されることを確認する
8. `.gml` ファイルをダブルクリックしてマップキャンバスに追加する

**期待される動作**:

- 各年度・地域ノードが展開可能である
- ZIP 内の `.gml` ファイルが階層付きで表示される
- ダブルクリックでレイヤがマップキャンバスに追加される
- エラー発生時は理解可能なメッセージが表示される

## 4. テスト実行

**前提条件**:

- QGIS 環境が正しくセットアップされている（`.venv` に QGIS Python がインストール済み）
- 仮想環境がアクティブである

**テスト実行方法**:

```bash
# 全テストを実行
.venv/bin/pytest tests/ -v

# 行政区域関連のテストのみ実行
.venv/bin/pytest tests/test_update_gyousei_kuiki.py tests/test_data_loader.py -v -k "gyousei_kuiki or n03"

# カバレッジ付きで実行
.venv/bin/pytest tests/ --cov=ksj --cov=scripts --cov-report=term-missing
```

**テスト結果の確認**:

- URL 生成テスト: N03 データが正しい URL を生成すること
- 拡張子フィルタテスト: `.gml` ファイルがサポートされていること
- 定義読み込みテスト: `gyousei_kuiki.json` が正しく読み込まれること
- データコレクション名テスト: `get_data_collection_name("gyousei_kuiki")` が「行政区域」を返すこと
- HTML パーステスト: N03 テーブルから年度・地域・ファイル名が正しく抽出されること

**スキップされるテスト**:

- QGIS 統合テスト: 実際の QGIS 環境でのみ実行可能（`pytest.mark.qgis` マーク付き）
- これらのテストは手動での QGIS 確認で代替される

## トラブルシューティング

**問題**: `update_gyousei_kuiki.py` がネットワークエラーで失敗する

**解決策**:

1. インターネット接続を確認する
2. プロキシ設定が必要な場合は、環境変数 `HTTP_PROXY`, `HTTPS_PROXY` を設定する
3. ローカル HTML ファイルから実行する: `python scripts/update_gyousei_kuiki.py --html-file /path/to/downloaded.html`

**問題**: QGIS ブラウザで行政区域が表示されない

**解決策**:

1. `gyousei_kuiki.json` が存在し、正しい JSON 形式であることを確認する
2. QGIS を再起動する
3. ブラウザパネルをリフレッシュする（F5 キー）
4. `get_data_collection_name("gyousei_kuiki")` が「行政区域」を返すことをテストで確認する

**問題**: ZIP ファイルが開けない、または `.gml` ファイルが表示されない

**解決策**:

1. GDAL がインストールされ、VSI 機能が有効であることを確認する
2. `.gml` が `supported_extensions` に含まれていることを `ksj/zip_scanner.py` で確認する
3. リモート ZIP の URL が正しいことを確認する（`build_download_url()` のテスト）

## 技術的詳細

**URL 生成戦略**:

- N03 データは独自のディレクトリ年決定戦略を使用: `_get_dir_year_from_input_yyyy()`
- 年度キーから `YYYY` を抽出し、URL パスに使用: `data/N03/N03-YYYY/<filename>`
- 戦略パターンにより、他のコレクション（A33 等）とは異なるロジックを共存可能

**ファイル形式サポート**:

- `.shp` (Shapefile): 従来からサポート
- `.geojson` (GeoJSON): 従来からサポート
- `.gml` (Geography Markup Language): Phase 2 で追加

**データ更新フロー**:

1. `update_gyousei_kuiki.py` が N03 HTML をパース
2. 年度・地域を正規化して `gyousei_kuiki.json` を生成
3. `load_data_collections()` がプラグイン起動時に JSON を読み込む
4. `KsjRootItem.createChildren()` が各コレクションをブラウザツリーに追加
5. ユーザーがノードを展開すると `build_download_url()` で URL を生成
6. `zip_scanner.py` がリモート ZIP をスキャンして `.gml` ファイルを検出

**保守性**:

- 新しいコレクション追加時は `update_gyousei_kuiki.py` を参考にツールを作成
- URL 戦略の追加は `_DIR_YEAR_STRATEGIES` に登録するだけ
- 新しい拡張子サポートは `supported_extensions` に追加するだけ
