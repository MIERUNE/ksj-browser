# Implementation Plan: 学校データのサポート追加

**Branch**: `003-school-data` | **Date**: 2026-01-14 | **Spec**: [specs/003-school-data/spec.md](../spec.md)
**Input**: Feature specification from `/specs/003-school-data/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

- 国土数値情報(P29 学校)の「地域/年/ファイル名」一覧を公式ページから抽出し、`gakkou.json`（年度 → 地域 →ZIP ファイル名）を自動生成/更新できる開発者向けツールを追加する。
- 生成された定義ファイルを同梱してブラウザパネルに表示し、年度・地域で選択してリモート ZIP から地図データを読み込めるようにする。
- P29 の URL 規則とテーブル構造を調査し、`update_gyousei_kuiki.py` と同様のアプローチを採用する。
- SHP が提供される場合は SHP を優先し、SHP が無い場合は GML を採用する（現状 P29 は GML のみ想定）。

## Technical Context

**Language/Version**: Python 3.9+（QGIS 3.28 同梱 Python を想定）  
**Primary Dependencies**: QGIS 3.x (PyQt, qgis.core), GDAL/OGR（VSI: /vsizip//vsicurl）、標準ライブラリ（argparse, json, html.parser, urllib）  
**Storage**: JSON ファイル（データコレクション定義）  
**Testing**: pytest + pytest-qgis  
**Target Platform**: QGIS 3.x（macOS / Windows / Linux）
**Project Type**: QGIS プラグイン（`ksj/` がビジネスロジック、`ui/` が UI、`tests/` が pytest）  
**Performance Goals**: 定義生成は ≤30 秒（SC-001）、ブラウザからの読み込み開始は ≤5 秒（SC-003）  
**Constraints**: 相対インポート必須、テスト駆動（憲章準拠）。実行時は同梱 JSON を参照（FR-016）。  
**Scale/Scope**: 追加コレクション 1 件（`gakkou`）＋関連する URL 生成/拡張子サポートの最小変更

### Test Running Notes

- macOS では `pytest` 実行前に `source setup_qgis_env.sh` を実行し、QGIS 関連の環境変数を設定する。
- `pytest-qgis` が必要な統合テストは、CI/通常の pytest 実行ではスキップされ得るため、最終確認は QGIS 上の手動確認で補完する。

## Constitution Check

_GATE: Must pass before Phase 0 research. Re-check after Phase 1 design._

GATE 結果（Phase 0 開始前）:

- ✅ Modular Design: 生成ツールは `scripts/`、プラグインロジックは `ksj/` に閉じる
- ✅ Test-First: 追加/変更するロジック（URL 生成、HTML パース、地域名正規化等）は pytest でテストを追加する
- ✅ Relative Imports: `ksj/` 内は相対インポートを維持する
- ✅ Type Safety: 既存の型ヒント方針に従い、追加関数にも型を付ける

再チェック（Phase 1 設計後）:

**結果**: ✅ すべてのゲートをパス。憲章違反なし。

**詳細**:

1. **Modular Design**: ✅

   - `scripts/update_gakkou.py`: 独立した生成ツール（単一責任）
   - `ksj/data_loader.py`: データ読み込み・URL 生成（既存モジュール拡張）
   - `ksj/browser.py`: ブラウザパネル表示（変更不要、定義ファイル追加のみ）
   - `tests/test_update_gakkou.py`: 専用テストファイル

2. **Test-First Development**: ✅

   - 全ての新規関数にユニットテストを追加
   - フィクスチャベースのテスト（`p29_sample.html`）
   - URL 生成の既存テストが壊れないことを確認
   - 契約書（contracts/）でテスト要件を明記

3. **Relative Imports**: ✅

   - `scripts/` は相対インポート不要（スタンドアロンスクリプト）
   - `ksj/` 内の変更は相対インポートを維持（`from . import data_loader`）

4. **Type Safety**: ✅
   - 新規関数に型ヒントを追加（`normalize_year(year_display: str) -> str`）
   - 既存の型ヒント方針を継続

**Complexity Tracking**: なし（憲章違反がないため複雑性追跡は不要）

## Project Structure

### Documentation (this feature)

```text
specs/003-school-data/
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
    gyousei_kuiki.json
    gakkou.json                 # NEW（生成物をコミットして同梱）

scripts/
  update_gyousei_kuiki.py
  update_gakkou.py               # NEW（開発者向け生成ツール）

tests/
  test_data_loader.py
  test_zip_scanner.py
  test_browser_items.py
  test_update_gakkou.py          # NEW（生成ツールのテスト）
```

**Structure Decision**: 既存の QGIS プラグイン構造を維持し、生成ツールは `scripts/` に追加、定義ファイルは `ksj/data_collections/` に同梱する。`update_gyousei_kuiki.py` のアプローチを学校データ（P29）に適用する。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation                  | Why Needed         | Simpler Alternative Rejected Because |
| -------------------------- | ------------------ | ------------------------------------ |
| [e.g., 4th project]        | [current need]     | [why 3 projects insufficient]        |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient]  |
