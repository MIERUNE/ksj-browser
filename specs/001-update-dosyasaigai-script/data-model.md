# Data Model: 土砂災害警戒区域（dosyasaigai_keikai_kuiki）

## 目的

MLIT A33 土砂災害警戒区域データの年度・都道府県別 ZIP ファイル一覧を JSON で保持し、QGIS ブラウザツリーの `コレクション → 年度 → 地域 → ZIP 内容` を構築する。

## Entity: DosyasaigaiCollection

- **storage**: `ksj/data_collections/dosyasaigai_keikai_kuiki.json`
- **shape**:

```json
{
	"2024年": {
		"北海道": "A33-24_01_SHP.zip",
		"青森": "A33-24_02_SHP.zip"
	},
	"2023年": {
		"北海道": "A33-23_01_GML.zip"
	}
}
```

## フィールド/バリデーション

- 年度キー: `^\d{4}年$` を必須。降順で並べる。
- 地域キー: `全国` または都道府県名（サフィックス無し、北海道のみ例外）。`
- ファイル名: `^A33-\d{2,4}_.+_(SHP|GML)\.zip$` を想定。SHP/GML いずれかが存在する。
- 形式選択: 同一年・地域に複数候補がある場合、`_SHP.zip` を優先。無い場合のみ `_GML.zip`。

## 関係/派生

- `ksj.data_loader.load_data_collections()` が JSON を読み込み、`collection_id="dosyasaigai_keikai_kuiki"` の辞書として提供。
- `build_download_url()` は 年度→4桁年 を抽出し `A33-YY` ディレクトリ配下のファイル URL を生成（既存戦略 `_get_dir_year_from_filename_yy` を使用）。
- ブラウザ UI は `KsjYearItem` → `KsjPrefectureItem` を構築し、ZIP 内ファイルは `zip_scanner.py` が列挙する。

## 状態遷移

1. 国土数値情報サイトが更新される
2. `update_dosyasaigai_keikai_kuiki.py` を実行し HTML からデータを再生成
3. JSON をコミット/配布
4. QGIS プラグインが最新 JSON を読み込み、ユーザーがブラウザで参照

## エラーハンドリング要件

- ネットワーク取得で例外発生時は JSON を変更せず終了コード 1
- テーブル未検出・必須列欠落で終了コード 2
- 書込み失敗（ディスク権限等）で終了コード 3
