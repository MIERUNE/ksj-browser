# Tasks: 土砂災害警戒区域データ更新スクリプト

**Input**: Design documents from `/specs/001-update-dosyasaigai-script/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: 各ユーザーストーリーで必要な pytest を明示し、TDD のガイドラインに従ってテストタスクを先行配置します。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 並行可能（異なるファイル、依存なし）
- **[Story]**: 対象ユーザーストーリー（US1/US2/US3）
- すべてのタスクに正確なファイルパスを含めます

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 新規スクリプトとテスト環境の骨組みを用意し、後続フェーズの実装土台を整える。

- [X] T001 作業用エントリを作成し、`scripts/update_dosyasaigai_keikai_kuiki.py` に shebang・main スタブ・argparse 雛形を追加する
- [X] T002 `tests/test_update_dosyasaigai_keikai_kuiki.py` と `tests/fixtures/a33_sample.html` を作成し、pytest から読み込めるようにパスヘルパを準備する

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 全ユーザーストーリーが共有する解析・正規化・構造化ロジックを先に完成させる（完了するまで以降のフェーズ着手不可）。

- [X] T003 `scripts/update_dosyasaigai_keikai_kuiki.py` に `A33TableParser`（`HTMLParser` 継承）を実装し、`mb30 responsive-table` テーブルから `year_display/region_raw/filename` を抽出できるようにする
- [X] T004 `scripts/update_dosyasaigai_keikai_kuiki.py` に `normalize_year()` と `normalize_region()` のユーティリティを実装し、和暦→西暦と都道府県サフィックス除去ルールをカバーする
- [X] T005 `scripts/update_dosyasaigai_keikai_kuiki.py` に `build_collection_structure()` を実装し、SHP 優先・年度降順・地域は A33 テーブルに出現した順序を保持する辞書を生成する共通ロジックを作成する
- [X] T006 `scripts/update_dosyasaigai_keikai_kuiki.py` に JSON 書き込みヘルパー（UTF-8, `indent="\t"`, エラー時例外送出）を用意し、後続の CLI から再利用できるようにする

**Checkpoint**: HTML 行抽出～JSON 生成のコアが完成。ここからユーザーストーリーごとの入出力に着手可能。

---

## Phase 3: User Story 1 - 一括更新を一度のコマンドで完了したい保守担当 (Priority: P1) 🎯 MVP

**Goal**: デフォルト URL から HTML を取得し、`dosyasaigai_keikai_kuiki.json` を最新状態で生成できる 1 コマンド更新を提供する。

**Independent Test**: `python scripts/update_dosyasaigai_keikai_kuiki.py` を実行し、47 都道府県を含む JSON が生成・終了コード 0 を返すことを確認する。

### Tests (先に実装)

- [X] T007 [P] [US1] `tests/test_update_dosyasaigai_keikai_kuiki.py` に実 HTML フィクスチャを用いた `extract_table_rows()`/`build_collection_structure()` の結合テストを追加し、SHP 優先と年度降順を検証する

### Implementation

- [X] T008 [US1] `scripts/update_dosyasaigai_keikai_kuiki.py` にデフォルト URL 取得 (`urllib.request`) と HTML→JSON パイプラインを実装し、`ksj/data_collections/dosyasaigai_keikai_kuiki.json` へ書き出す
- [X] T009 [US1] 実行完了時に抽出行数・年度数・都道府県数を `print()` するサマリーログを追加し、Quickstart から確認できるよう `specs/001-update-dosyasaigai-script/quickstart.md` を更新する

**Checkpoint**: ネットワーク経由の一括更新が完了し、JSON 差分の確認・配布が可能。

---

## Phase 4: User Story 2 - オフライン検証を行う QA エンジニア (Priority: P2)

**Goal**: `--html-file` 指定時にネットワークへアクセスせずローカル HTML のみで JSON を生成できるようにする。

**Independent Test**: `python scripts/update_dosyasaigai_keikai_kuiki.py --html-file tests/fixtures/a33_sample.html --output tmp.json` を実行し、ネットワークアクセス無しで JSON が生成されることを確認する。

### Tests

- [X] T010 [P] [US2] `tests/test_update_dosyasaigai_keikai_kuiki.py` に `--html-file` 優先ロジックを検証するユニットテストを追加し、`--url` と併用した場合でもローカルファイルのみを使用することを確認する

### Implementation

- [X] T011 [US2] `scripts/update_dosyasaigai_keikai_kuiki.py` の CLI で `--html-file` 指定時にファイル読み込みを優先し、ネットワーク取得を完全にバイパスする分岐を実装する
- [X] T012 [US2] `specs/001-update-dosyasaigai-script/quickstart.md` のオフライン手順とテスト節を更新し、`--html-file` での再現フローを明示する

**Checkpoint**: 保存済み HTML だけで回帰テストが行える状態になり、CI や手元での再現性が向上。

---

## Phase 5: User Story 3 - 自動化パイプラインを監視するリリース担当 (Priority: P3)

**Goal**: ネットワーク失敗・テーブル未検出・書込み失敗を検知して適切な終了コードとログを返し、パイプラインで異常が把握できるようにする。

**Independent Test**: pytest で無効 URL / 空 HTML / 書込み不可パスをそれぞれ指定し、終了コード 1/2/3 とメッセージが得られることを確認する。

### Tests

- [X] T013 [P] [US3] `tests/test_update_dosyasaigai_keikai_kuiki.py` にネットワーク例外モック・空 HTML・書込み拒否を再現するテストを追加し、各ケースで終了コード 1/2/3 が返ることを検証する

### Implementation

- [X] T014 [US3] `scripts/update_dosyasaigai_keikai_kuiki.py` に try/except を追加し、ネットワーク/パース/書込みエラーごとにエラーメッセージを出力して `sys.exit(1|2|3)` を返すエラーハンドリングを実装する
- [X] T015 [US3] `specs/001-update-dosyasaigai-script/quickstart.md` のトラブルシューティング節を更新し、終了コード別の対処方法を追記する

**Checkpoint**: スクリプトが失敗時にも安全に停止し、CI が確実に異常を検出できる。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 仕上げと横断的なフォローアップ。

- [X] T016 README.md と `ksj-browser` 全体のドキュメントに新スクリプトの利用方法（例: プロジェクト構成セクション）を追記する
- [X] T017 `.venv/bin/pytest tests/test_update_dosyasaigai_keikai_kuiki.py -v` を実行し、Quickstart 記載のテストコマンドが成功することを記録する

---

## Dependencies & Execution Order

1. **Phase 1 Setup** → 2. **Phase 2 Foundational** → 3. **Phase 3 (US1)** → 4. **Phase 4 (US2)** → 5. **Phase 5 (US3)** → 6. **Polish**
2. 各ユーザーストーリーは Foundational 完了後に着手可能。
3. US1 (MVP) 完了後に US2/US3 を並行開始してもよい（US2=オフライン対応、US3=エラーハンドリング）。

## Parallel Execution Opportunities

- **T007/T010/T013** はそれぞれ独立した pytest 追加のため並列実装可能（異なるテストケース）。
- **US2** と **US3** の実装タスク（T011 vs. T014）も異なるコードパスのため、US1 完了後に別メンバーで同時進行できる。
- ドキュメント更新タスク（T012, T015, T016）はコード完了後にまとめて並走可能。

## Implementation Strategy

1. **MVP**: Phase 1→2→3 を完了し、オンライン一括更新 + サマリーログを提供する。
2. **Incremental**: MVP 後に US2（オフライン入力）と US3（エラー検知）を追加し、それぞれを独立にテスト・デモする。
3. **Parallel Teaming**: Foundational 完了後、開発者 A が US2、開発者 B が US3 を担当し、最終的に Polish フェーズでドキュメント・検証を統合する。
