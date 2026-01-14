# Contract: dosyasaigai_keikai_kuiki.json

## 目的

QGIS ブラウザが土砂災害警戒区域データを年度→地域の階層で表示し、ZIP ファイルにアクセスできるようにする。

## スキーマ

```json
{
	"YYYY年": {
		"都道府県名": "A33-YY_PP_FORMAT.zip"
	}
}
```

- 年度キー: 4 桁 + `年`
- 地域キー: `全国` または都道府県。`東京都` → `東京`, `京都府` → `京都` 等。
- 値: ファイル名（SHP 優先、Fallback GML）。

## 生成・更新

- `scripts/update_dosyasaigai_keikai_kuiki.py` が唯一の公式生成手段
- Git にコミットし、プラグイン配布物に同梱

## 利用側契約

- `ksj.data_loader.load_data_collections()` は JSON を辞書として返す
- `build_download_url()` は年キーから 4 桁を抽出し、`https://nlftp.mlit.go.jp/ksj/gml/data/A33/A33-YY/<filename>` を生成
- ブラウザ UI は年度降順で並べ、地域は 50 音順に並べる

## 検証

- JSON は UTF-8 / LF / インデント 1 タブ
- 47 都道府県 + 全国（必要に応じて）が揃う
- テスト `tests/test_update_dosyasaigai_keikai_kuiki.py` でサンプル HTML から同じ構造が生成される
