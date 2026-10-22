# WARP 向け開発ガイド

国土数値情報（KSJ）をQGISのブラウザパネルから利用するプラグインです。
開発規約は [AGENTS.md](AGENTS.md)、現行構成・利用方法・更新コマンドは [README.md](README.md) を参照してください。

## データの流れ

1. `scripts/update_catalog.py` が公式一覧・詳細ページ・旧版を収集し、`ksj/catalog/` に全件カタログを生成します。
2. `ksj/catalog.py` が索引とデータセット別JSONを遅延読み込みします。
3. `ksj/browser.py` と `ksj/catalog_browser.py` が分類・データ・年度・地域・配布ファイルを表示します。
4. `ksj/local_storage.py` が指定フォルダへ配布データを取得・解凍し、`ksj/zip_scanner.py` が読み込み候補を探索します。
5. 通常のローカルファイルとしてQGISへレイヤーを追加します。メッシュからの選択は `ksj/mesh_index.py` が担当します。

## 検証

QGIS付属Pythonとシステムサイトパッケージを共有する仮想環境を使い、別のPyQtをインストールしないでください。

```bash
source setup_qgis_env.sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q --cov=ksj --cov=scripts --cov-report=term-missing
uv run ruff check .
```

全件カタログの仕様と検証記録は [specs/004-complete-catalog/](specs/004-complete-catalog/) にあります。旧3コレクション向けのコードとJSONは廃止済みです。`specs/001-*`〜`specs/003-*` は設計履歴として扱ってください。
