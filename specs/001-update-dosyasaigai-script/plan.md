# Implementation Plan: 土砂災害警戒区域データ更新スクリプト

**Branch**: `001-update-dosyasaigai-script` | **Date**: 2026-01-14 | **Spec**: [specs/001-update-dosyasaigai-script/spec.md](specs/001-update-dosyasaigai-script/spec.md)
**Input**: Feature specification from `/specs/001-update-dosyasaigai-script/spec.md`

## Summary

A new CLI utility `scripts/update_dosyasaigai_keikai_kuiki.py` will scrape the MLIT A33 dataset page, normalize year/prefecture information, prioritize SHP over GML, and update `ksj/data_collections/dosyasaigai_keikai_kuiki.json`. It mirrors the existing `update_gyousei_kuiki.py` tool, supporting offline HTML input and explicit exit codes for operational safety.

## Technical Context

**Language/Version**: Python 3.9 (QGIS 3.28 同梱)
**Primary Dependencies**: 標準ライブラリ (argparse, json, html.parser, urllib) / 既存 `scripts/update_gyousei_kuiki.py` と同一方針
**Storage**: JSON ファイル (`ksj/data_collections/dosyasaigai_keikai_kuiki.json`)
**Testing**: pytest + pytest-qgis
**Target Platform**: macOS (QGIS 3.x dev env), CI, 任意の POSIX
**Project Type**: QGIS プラグイン（リポジトリ内 CLI スクリプト追加）
**Performance Goals**: 1 実行あたり <30s、ネットワーク要求 1 回、47 都道府県カバレッジ 100%
**Constraints**: ネットワーク失敗時/HTML 欠損時は安全に中断し exit code 1/2/3 を返す。`--html-file` 指定時はネットワークアクセス禁止。
**Scale/Scope**: 年 1 回程度の更新、JSON サイズ ~500KB

## Constitution Check

- ✅ QGIS Plugin Architecture: 既存スクリプト群への追加。プラグイン API 未変更 → 準拠
- ✅ Modular Design: `scripts/` 内 CLI と `ksj/` JSON 定義のみ変更 → 分離維持
- ✅ Test-First Development: `tests/test_update_dosyasaigai_keikai_kuiki.py` を追加して TDD 実施予定 → OK
- ✅ Relative Imports: スクリプトはローカル参照のみで相対インポート不要 → OK
- ✅ Type Safety: 主要ロジックで型ヒントを導入、cast 不要 → OK

Phase 1 設計後の再確認結果も同上（違反なし）。

## Project Structure

```text
specs/001-update-dosyasaigai-script/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md (別コマンド)
```

Repository:

```text
scripts/
├── update_gyousei_kuiki.py
└── update_dosyasaigai_keikai_kuiki.py (new)

ksj/
└── data_collections/
    └── dosyasaigai_keikai_kuiki.json (auto-updated)

tests/
└── test_update_dosyasaigai_keikai_kuiki.py (new)
```

**Structure Decision**: 単一リポジトリ内で CLI スクリプト + JSON データの既存構成を踏襲。追加フォルダは不要。

## Complexity Tracking

(なし)

## Phase 0: Research & Clarifications

- **テーブル抽出戦略**: `mb30 responsive-table` を指標に HTMLParser で列抽出（`research.md` 参照）。
- **入力優先順位**: `--html-file` > `--url` > デフォルト URL。テスト再現性を最優先。
- **形式選択と正規化**: 年度は `YYYY年`、地域は既存キーと同じ正規化、SHP 優先ルールを再確認。
- **終了コード/ログ**: 行政区域ツールのコード体系を踏襲し、CI 監視を簡素化。

未解決事項はなく、Phase 1 へ進行可能。

## Phase 1: Design & Contracts

- **Data Model** (`data-model.md`): `DosyasaigaiCollection` を定義し、年度キー/地域キー/ファイル名のバリデーションと書式を整理。
- **Contracts** (`contracts/update-tool.md`, `contracts/data-collection.md`): 入力オプション、優先順位、出力形式、終了コードを明文化。
- **Quickstart** (`quickstart.md`): ツール実行手順、テストコマンド、QGIS での確認フロー、トラブルシューティングを整理。
- **Agent Context**: `.specify/scripts/bash/update-agent-context.sh codex` 実行済み。Codex CLI 用に Python/QGIS/JSON 依存を追記。

## Phase 2: Implementation Outline

1. **スケルトン & CLI**
   - `scripts/update_dosyasaigai_keikai_kuiki.py` を作成。
   - argparse で `--url`, `--html-file`, `--output` を定義し、`main()` が終了コードを返す構造にする。

2. **入力決定 & 取得層**
   - `--html-file` 指定時はファイル読み込み→HTML 文字列化。
   - それ以外は URL（デフォルト含む）を `urllib.request` + User-Agent で取得。例外を捕捉してコード 1。

3. **HTML パース**
   - `update_gyousei_kuiki.py` を参考に `HTMLParser` サブクラス `A33TableParser` を実装。
   - `mb30 responsive-table` の `tbody` から行を抽出し、`year_display`, `region_raw`, `filename` リストを返す。

4. **正規化 & 構造化**
   - `normalize_year()` と `normalize_region()` を実装し単体テスト。
   - `build_collection_structure()` で SHP 優先選択と年度/地域ソートを行い、辞書を生成。
   - 抽出行数や年度数をログ出力。

5. **JSON 書き込み**
   - `json.dump(..., ensure_ascii=False, indent="\t", sort_keys=False)` で書き込み。
   - 書き込み失敗時はコード 3。

6. **テスト**
   - `tests/test_update_dosyasaigai_keikai_kuiki.py` を追加し、HTML 抽出/正規化/SHP 優先/エラーコードを網羅。
   - 既存 `tests/test_data_loader.py` に A33 データの回帰テストを追加（URL 生成が変わらないことを確認）。

7. **ドキュメント/チェック**
   - `quickstart.md` の手順で手動確認。
   - 生成 JSON の diff を確認し、必要に応じてコミット。
