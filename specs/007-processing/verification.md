# Processing連携の検証記録

検証日: 2026-10-22

## 環境

- macOS、QGIS 3.42.1-Münster、Qt 5.15.2、QGIS付属Python 3.9.5
- QGIS本体のPythonとシステムサイトパッケージを利用。依存パッケージ・カタログJSON・qtaroのコードは変更していない。
- QGIS 4 / Qt 6 は実機未検証。

## 初回実装の自動テスト

```bash
source setup_qgis_env.sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q \
  --cov=ksj --cov=scripts --cov-report=term-missing
uv run --frozen ruff check .
.venv/bin/ruff format --check ksj/processing_algorithms.py \
  ksj/processing_provider.py plugin.py tests/test_processing.py
git diff --check
```

- pytest: **132件成功**（既存110件、新規22件）。
- `ksj` / `scripts` 全体の行カバレッジ: **86%**。新規アルゴリズム: **94%**。
- Ruff、変更Pythonファイルのフォーマット、差分チェック: 成功。
- 既存のpytest-cov非推奨警告2件と、重複ZIPエントリを作るテストの警告1件が出る。
- HTTPを使うテストはループバックサーバーが必要。実行環境のサンドボックスでは起動が制限されたため、許可された制限外実行で検証した。
- `uv run` による意図しないロック更新は取り消し、最終Lintは `--frozen` を使用した。

## 確認した契約

- 同梱カタログの検索→データセットID→配布一覧の到達。
- AND検索・部分一致・ページング・範囲外のページ指定・無効ID。
- 配布URL由来の安定ID、年度・地域・公式説明・利用条件情報の保持。
- 保存先の明示指定と既存設定の利用、未設定時のエラー、ダイアログ不要。
- ZIP取得・展開、同一配布の再利用、HTMLエラー応答、キャンセル時の未完成データ破棄。
- 実HTTP取得を `QgsProcessingAlgRunnerTask` のワーカーで実行。
- GeoJSONの日本語属性・CRS・地物数を保持し、`native:reprojectlayer` へ渡す。
- 複数レイヤーを持つGeoPackageとGeoTIFFを同梱したZIPの列挙・個別読み込み。
- 非空間KS-META XMLの除外、未対応XMLの警告・一覧化、レイヤーがない場合の取得結果。
- 単一 `QgsProcessingOutputMapLayer` をコンテキストから引き取り、プロジェクトに追加。
- `initProcessing` と `initGui` の複数呼び出し、unload、再登録。GUIなしの初期化。

## qtaro実装との結合確認

隣接するqtaroの `core.processing_catalog.processing_catalog` と
`core.runtime.BackgroundProcessing` を実際に読み込み、一時的な結合テストを実行した（**1件成功**）。qtaroへの変更は行っていない。

1. qtaroのツール一覧で4つの `ksj:*` が検出される。
2. `BackgroundProcessing("ksj:download_resource", ...)` で取得・展開し、完了サマリーのJSONからレイヤーURIを取得する。
3. `BackgroundProcessing("ksj:load_layer", ...)` で1レイヤーを読み込み、qtaroによるプロジェクトへの自動追加とIDの返却を確認する。
4. そのIDからレイヤーを取得し、QGIS標準の再投影を実行する。

この結合テストの配布ファイルは固定のテストZIPを使用した。公開サイトからのライブ取得や、LLMが自然言語指示から操作を選ぶ挙動は検証に含めていない。HTTP取得そのものは上記の自動テストで検証している。通常ダイアログの確認は後述。

## レビュー

独立レビューで必須修正事項なし。qtaroの所有権移譲、スレッド、検索・配布選択、登録解除の契約を確認した。実カタログの「東京／東京都」「シェープファイル形式／SHP」等の表記揺れについては、条件を減らして候補を確認する方法をREADMEに追記した。

## 選択式UIの追加検証

通常のProcessingダイアログで、名称・分類・版、年度・地域・形式を選択可能にした。取得画面では絞り込みと配布選択、読み込み画面ではファイルとサブレイヤー選択を行える。GUI専用のアルゴリズムコピーだけにウィジェットを設定し、Python・バッチ・モデルの文字列パラメータを維持している。

実QGISのダイアログで以下を確認した。

- 表示名から安定したデータセットID・配布IDへの変換。
- データセット変更・名前の入力途中で古い配布選択を解除。
- 年度→地域→形式の候補更新、未記載年度と「すべて」の区別。
- 同一表示名でも選んだ候補の値を保持し、従属項目を更新。
- 配布IDとGeoPackageサブレイヤーの履歴復元。
- GeoJSON・GeoPackage・GeoTIFFの列挙、ラスタの種類の自動設定。
- 不正ファイル・削除された履歴レイヤーの未選択化と再選択。
- GUIの読み込み成功時だけ、標準の結果処理に地図追加を予約。
- GUI表示後もレジストリおよびバッチ用コピーの入力定義を変更しない。

GUIの回帰テストは `tests/test_processing_widgets.py` の13件。独立レビューで見つかった「履歴のレイヤーが存在しないと先頭レイヤーへ置換される」問題は、修正前のテスト失敗を確認し、不一致時の選択解除と説明表示で修正した。

修正後の全pytestは **145件成功**、`ksj` / `scripts` 全体の行カバレッジは **88%**（アルゴリズム98%、入力画面95%）。Ruff、変更Pythonファイルのフォーマット、差分チェックも成功。上記と同じ既存警告3件のみ。再レビューでは関連テスト2件を独立実行し、追加指摘なし。

同梱カタログのダムデータを選んだダイアログをオフスクリーン描画し、[画面画像](../../imgs/processing-download.png)を目視確認した。名称・年度・地域・測地系・容量・保存先が読めることを確認。OSのファイル参照ダイアログの手動操作、およびQGIS 4 / Qt 6の実機確認は実施していない。

READMEは一般利用者向けの操作手順に書き換え、qtaro・AIエージェント対応への言及を削除した。
