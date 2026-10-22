# 展開済みファイル保存の実装計画

> **For agentic workers:** Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一時取得したZIPを展開し、通常ファイルとして保存してマップへ追加する。
**Architecture:** `local_storage.ensure_local_data` はZIPなら展開完了ディレクトリ、単体配布ならファイルを返す。ブラウザとメッシュはこの戻り値を走査してファイルの実パスをレイヤーへ渡す。
**Tech Stack:** Python 3.9標準zipfile/pathlib/tempfile、既存QGIS/Qt。
**Spec:** `docs/superpowers/specs/2026-10-22-extracted-files-design.md`

## 制約・レビュー観点

- 初回設定・再利用、通信の重複抑止、通常ファイルの参照を維持する。
- Shapefile付属ファイルとGMLスキーマを保持する。
- 入れ子ZIP、UTF-8/CP932名を通常ファイルへ変換する。
- 破損、中止、パス逸脱、リンク、名前衝突では未完成データを残さない。
- 旧ZIPからの展開は通信せず、旧レイヤーの原本を保持する。
- プロジェクトと保存先を一緒に移動しても地物・属性が読める。

## Task 1: 取得・展開の変更

**Files:** `ksj/local_storage.py`, `tests/test_local_storage.py`, `tests/test_extracted_storage.py`
**Interface:** `ensure_local_data(url, directory, is_canceled=None, progress=None) -> str`

- [x] 展開・付属ファイル・既存ZIP・中止・不正パスの回帰テストを追加して失敗を確認する。
- [x] 一時ZIPの取得、検証を兼ねた再帰展開、完成ディレクトリの原子的な確定を実装する。
- [x] 対象テストで成功と一時ZIPの削除、再利用時の通信ゼロを確認する。

## Task 2: ブラウザ・メッシュの通常パス化

**Files:** `ksj/catalog_browser.py`, `ksj/mesh_index.py`, 関連テスト。
**Consumes:** Task 1の戻り値。ZIP内のVSI走査をファイルシステム走査に置き換える。

- [x] ブラウザ・メッシュの実ファイルURIと入れ子データの配置変更テストを先に更新し失敗を確認する。
- [x] ローカルファイル一覧から既存階層とレイヤーを作り、実QGISで再読込・配置変更を確認する。

## Task 3: 検証・ドラフトPR更新

- [x] 全pytest（`--cov=ksj --cov=scripts --cov-report=term-missing`）、Ruff、diffチェックを実行する。
- [x] README・設計・検証記録を更新し、別エージェントによる全体レビューを受ける。

更新対象: ドラフトPR #10。検証済み差分をコミット・プッシュし、説明を展開済みファイル方式へ更新する。

## 実行記録

- Task 1: 展開の16件を未実装で失敗させ、実装後に成功。
- Task 2: ブラウザ/メッシュ連携の失敗を確認して変更。通常フォルダのGDAL走査に `.` / `..` が含まれる問題を別の回帰テストで再現し、除外して修正。関連61件が成功。
- 既存のPRブランチで変更を継続し、新しい作業ツリーは作成しない。
- Task 3: 全139件、カバレッジ83%、Ruff、diffチェックが成功。別エージェントのレビューに修正必須・軽微の指摘なし。
