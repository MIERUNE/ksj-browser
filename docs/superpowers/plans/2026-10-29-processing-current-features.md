# Processing 現行機能対応の実装計画

> 実装担当: `superpowers:executing-plans` に沿って順に実行。詳細設計・実装は利用者から一任済み。

**Goal:** ZIP 部分取得と現行の読み込み機能を Mapsuke から使える Processing API にする。

**Architecture:** remote_zip / local_storage を共用し、取得 API を processing_resources.py に分ける。レイヤー作成と索引作成は GUI 副作用のない関数を共有する。

**Tech Stack:** Python、QGIS/PyQt/GDAL、pytest-qgis。

**Spec:** ../specs/2026-10-29-processing-current-features-design.md

## 制約

- QGIS 3.44・4.x。新規外部依存なし。既存アルゴリズムの既定動作は維持。
- ダイアログなし、処理本体でプロジェクト変更なし。部分取得失敗時に全体取得しない。
- 日本語の説明・エラー。Mapsuke の説明冒頭 48 文字で用途が分かる。

## レビュー重点

- 一時領域とコンテキストの寿命差: 結果レイヤーを移譲後も実データを読める。
- 不正な MEMBER / 入れ子 ZIP / VRT: 全体取得せず明確なエラー。
- 部分保存と全体保存: 既存キャッシュを壊さず再利用。
- サブレイヤーと文字コード: 指定した対象だけを正しい属性で読める。
- メッシュ索引: 年度の絞り込みと全件生成、空集合時のエラー。

### Task 1: ZIP 一覧・選択取得

Files: ksj/processing_resources.py（追加）、ksj/processing_algorithms.py、ksj/processing_provider.py、tests/test_processing_resources.py（追加）。

Interfaces: `ListResourceFiles` は `RESULTS.items[].member` を返す。`DownloadResource` は MEMBER / TEMPORARY を受ける。既存 RESULTS.layers の契約を維持。

- [x] 実 HTTP Range の一覧・部分取得・付属ファイル・再利用・失敗・取消の回帰テストを追加し、未実装による失敗を確認。
- [x] 共通の配布解決、保存先解決、取得関数と ListResourceFiles を実装し DownloadResource に接続。
- [x] Processing 関連テストを Docker で成功させる。

### Task 2: 直接レイヤー出力

Files: ksj/processing_resources.py、ksj/processing_algorithms.py、ksj/processing_widgets.py、tests/test_processing_resources.py、tests/test_processing_widgets.py。

Interfaces: `LoadResource` は Task 1 の取得関数を利用。LAYERS は QgsProcessingOutputMultipleLayers。共通 `create_layer(source, provider, name, encoding, context, feedback)` を LoadLayer と共有。

- [x] バックグラウンドで一時取得→出力レイヤー移譲、ラスタ、サブレイヤー、文字コードのテストを追加し失敗確認。
- [x] LoadResource と GUI の複数出力処理を実装。
- [x] 対象テストを成功させる。

### Task 3: メッシュ索引・説明・全体検証

Files: ksj/processing_mesh.py（追加）、ksj/mesh_index.py、ksj/processing_provider.py、README.md、tests/test_processing_resources.py、tests/test_processing.py。

Interfaces: GUI 副作用のない `create_mesh_index(title, resources)` をブラウザ・Processing で共用。Processing は OUTPUT を返す。

- [x] 年度絞り込み、索引属性・範囲、空集合、バックグラウンド実行のテストを追加し失敗確認。
- [x] 索引作成を共用し Processing 登録・ヘルプ・README の呼び出し例を更新。
- [x] QGIS 3.44・4.0・4.2 全テスト、カバレッジ、Lint・Bandit・Qt6 互換検査を実行。
- [x] 独立レビューの指摘を確認し、必要な回帰テストと修正を行う。

## 進捗

- 基準: Processing 関連 48 件成功。作業開始時の作業ツリーは clean。
- 判断: 既存チェックアウトに作業ブランチを作成し、利用者が共有する作業場所で実装する。

- Task 1・2: 完了。選択取得の実 HTTP 回帰 13 件、直接出力・索引を含む関連テスト 124 件で確認。
- Task 3: 実装・説明・独立レビュー・最終検証完了。
- レビューの P2: 目次の付属ファイル確認が二乗時間だったため、フォルダ・基底名で一度索引化。走査回数の回帰テストを RED→GREEN。レビュー担当の同条件観測で 1,000 一式・1件検索が 23.238 秒→0.133 秒。ホスト QGIS 3.42 の性能観測であり対応版の互換性判定には不使用。
- テスト寿命管理: 正常取得したレイヤーを保持したまま例外を検証するテストが、QGIS 3.44 の終了時に異常終了。後続の例外検証前に出力レイヤーを解放し、単独・全件の実行とも終了コード 0。ダウンロード本体の変更は不要だったため撤回。

## 最終検証結果

- QGIS 3.44: `bash scripts/test-docker.sh -q --cov=ksj --cov=scripts --cov-report=term-missing` — 428 passed / 10 skipped、終了コード 0。
- QGIS 4.0・4.2: 同コマンドに `QGIS_TEST_IMAGE=qgis/qgis:4.0-trixie` / `qgis/qgis:4.2-trixie` — 各 438 passed、終了コード 0。
- 3.44 の skip は Docker イメージに git がないための既存配布 ZIP テスト。4.0・4.2 では実行済み。
- カバレッジ: 全体 88%、processing_resources.py 99%、processing_algorithms.py 98%。画面キャプチャ用スクリプトも全体集計に含む。
- Ruff check / format、Bandit（Low 以上）、公式 pyqgis4-checker の dry_run、git diff --check 成功。
- 非致命的な既存警告は GDAL の将来の例外設定変更と、衝突 ZIP を作るテストの重複ファイル名。
