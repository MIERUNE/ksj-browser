# Implementation Plan: 行政区域データのサポート追加

**Branch**: `002-admin-area-data` | **Date**: 2026-01-11 | **Spec**: [specs/002-admin-area-data/spec.md](specs/002-admin-area-data/spec.md)
**Input**: Feature specification from `/specs/002-admin-area-data/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

- 国土数値情報(N03 行政区域)の「地域/年/ファイル名」一覧を公式ページから抽出し、`gyousei_kuiki.json`（年度 → 地域 →ZIP ファイル名）を自動生成/更新できる開発者向けツールを追加する。
- 生成された定義ファイルを同梱してブラウザパネルに表示し、年度・地域で選択してリモート ZIP から地図データを読み込めるようにする。
- N03 は URL 規則が既存(A33)と異なるため、ダウンロード URL 生成ロジックを拡張する。
- SHP が提供される場合は SHP を優先し、SHP が無い場合は GML を採用する（現状 N03 は GML のみ想定）。

## Technical Context

**Language/Version**: Python 3.9+（QGIS 3.28 同梱 Python を想定）  
**Primary Dependencies**: QGIS 3.x (PyQt, qgis.core), GDAL/OGR（VSI: /vsizip//vsicurl）  
**Storage**: JSON ファイル（データコレクション定義）  
**Testing**: pytest + pytest-qgis  
**Target Platform**: QGIS 3.x（macOS / Windows / Linux）
**Project Type**: QGIS プラグイン（`ksj/` がビジネスロジック、`ui/` が UI、`tests/` が pytest）  
**Performance Goals**: 定義生成は ≤30 秒（SC-001）、ブラウザからの読み込み開始は ≤5 秒（SC-003）  
**Constraints**: 相対インポート必須、テスト駆動（憲章準拠）。実行時は同梱 JSON を参照（FR-016）。  
**Scale/Scope**: 追加コレクション 1 件（`gyousei_kuiki`）＋関連する URL 生成/拡張子サポートの最小変更

### Test Running Notes

- macOS では `pytest` 実行前に `source setup_qgis_env.sh` を実行し、QGIS 関連の環境変数を設定する。
- `pytest-qgis` が必要な統合テストは、CI/通常の pytest 実行ではスキップされ得るため、最終確認は QGIS 上の手動確認で補完する。

## Constitution Check

_GATE: Must pass before Phase 0 research. Re-check after Phase 1 design._

GATE 結果（Phase 0 開始前）:

- ✅ Modular Design: 生成ツールは `scripts/`、プラグインロジックは `ksj/` に閉じる
- ✅ Test-First: 追加/変更するロジック（URL 生成、拡張子フィルタ、正規化等）は pytest でテストを追加する
- ✅ Relative Imports: `ksj/` 内は相対インポートを維持する
- ✅ Type Safety: 既存の型ヒント方針に従い、追加関数にも型を付ける

再チェック（Phase 1 設計後）: ✅ 追加設計は憲章違反なし（想定）。

再チェック結果（Phase 1 成果物作成後）:

- ✅ Modular Design: 仕様上も `scripts/`（生成）と `ksj/`（実行）を分離
- ✅ Test-First: 追加変更点はテスト追加対象として明記（Phase 2 で具体化）
- ✅ Relative Imports / Type Safety: 既存の方針を変更しない

## Project Structure

### Documentation (this feature)

```text
specs/002-admin-area-data/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
ksj/
  browser.py
  data_loader.py
  zip_scanner.py
  data_collections/
    dosyasaigai_keikai_kuiki.json
    gyousei_kuiki.json      # NEW（生成物をコミットして同梱）

scripts/
  update_gyousei_kuiki.py   # NEW（開発者向け生成ツール）

tests/
  test_data_loader.py
  test_zip_scanner.py
  test_browser_items.py
```

**Structure Decision**: 既存の QGIS プラグイン構造を維持し、生成ツールは `scripts/` に追加、定義ファイルは `ksj/data_collections/` に同梱する。

## Phase 2: Implementation Outline

1. 生成ツール追加（`scripts/update_gyousei_kuiki.py`）

- 対象 URL から HTML 取得（User-Agent 指定）
- テーブル行を抽出し、`YYYY年`・地域名・ファイル名に正規化
- 同一年・同一地域の重複候補は SHP 優先/無ければ GML で解決
- `ksj/data_collections/gyousei_kuiki.json` を上書き生成（UTF-8、順序はページ順を維持）

2. 定義読み込み・表示名の追加

- `ksj/data_collections/gyousei_kuiki.json` を同梱
- `ksj/data_loader.get_data_collection_name()` に `gyousei_kuiki: 行政区域` を追加

3. ダウンロード URL 生成の拡張とリファクタリング
   - `ksj/data_loader.build_download_url()` を N03（`gyousei_kuiki`）対応
   - ディレクトリ年決定ロジックを戦略パターンでリファクタリング
     - `_get_dir_year_from_filename_yy()`: 既存パターン（A33 等、ファイル名から抽出）
     - `_get_dir_year_from_input_yyyy()`: N03 パターン（入力年から 4 桁）
     - `_DIR_YEAR_STRATEGIES` 辞書でデータ ID と戦略をマッピング
   - 既存テストが通ることを確認し、N03 用の新規テストを追加
4. ZIP 内拡張子サポート

- `ksj/zip_scanner.filter_supported()` に `.gml` を追加（GML フォールバック利用のため）

5. テスト追加（TDD）

- URL 生成（A33 の既存挙動が壊れない + N03 が通る）
- `.gml` が対象拡張子として抽出される
- `load_data_collections()` が `gyousei_kuiki.json` を取り込める
