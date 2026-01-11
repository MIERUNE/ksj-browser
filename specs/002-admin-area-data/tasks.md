# Tasks: 行政区域データのサポート追加

**Input**: Design documents from `specs/002-admin-area-data/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: この機能では、spec/plan で TDD が明示されているためテストタスクを含めます。

**Organization**: タスクはユーザーストーリー単位でグルーピングし、それぞれ独立に実装・テスト可能な増分になるように構成します。

## Format: `[ID] [P?] [Story] Description`

- `[P]`: 並列実行可能なタスク（他の [P] タスクとファイル競合がなく依存関係がない場合のみ付与）
- `[Story]`: このタスクが属するユーザーストーリー（US1, US2）
- 説明には必ず具体的なファイルパスを含める

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 既存プラグイン環境とテスト基盤が正常に動作していることを確認し、本フェーズの実装作業の前提を整える。

- [x] T001 既存プラグインのスモークテストを実行して現状がグリーンであることを確認する（macOS は `source setup_qgis_env.sh` 後に `pytest tests/test_smoke.py`）
- [x] T002 QGIS 用フィクスチャとブラウザ項目テストが実行可能であることを確認する（`tests/conftest.py`, `tests/test_browser_items.py`）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: URL 生成と ZIP スキャンといった複数コレクションで共有する基盤ロジックを拡張し、将来 20 以上のコレクション追加にも耐えられる状態にする。

**⚠️ CRITICAL**: このフェーズが完了するまでは、新旧コレクションの URL 生成と ZIP 内ファイル検出の挙動が不安定になるため、ユーザーストーリーの実装を進めない。

- [x] T003 ディレクトリ年決定の戦略関数（例: `_get_dir_year_from_filename_yy`, `_get_dir_year_from_input_yyyy`）と `_DIR_YEAR_STRATEGIES` マッピングを `ksj/data_loader.py` に実装し、`build_download_url()` から利用するようにリファクタリングする
- [x] T004 既存データコレクション（例: A33）について `build_download_url()` の回帰テストを追加し、戦略パターン化後も同じ URL が生成されることを `tests/test_data_loader.py` に検証する
- [x] T005 N03 用のディレクトリ年決定戦略と URL 形式（`.../data/N03/N03-YYYY/<filename>`）をカバーするテストケースを `tests/test_data_loader.py` に追加する
- [x] T006 ZIP 内ファイルの拡張子フィルタに `.gml` を追加し、`.shp`/`.geojson` を含めたサポート拡張子セットを `ksj/zip_scanner.py` の `filter_supported()` で更新する
- [x] T007 `.gml` ファイルがリモート ZIP から検出されること、および `.shp`/`.geojson` の既存挙動が変わらないことを確認するテストを `tests/test_zip_scanner.py` に追加する

**Checkpoint**: URL 生成ロジックと ZIP スキャナの基盤が安定し、新旧コレクションの回帰テストがすべてグリーンになっている。

---

## Phase 3: User Story 1 - データ更新ツールの実行 (Priority: P1) 🎯 MVP

**Goal**: 開発者が `scripts/update_gyousei_kuiki.py` を実行するだけで、N03 ページから行政区域データの「年度 × 地域 → ZIP ファイル名」定義を自動生成/更新できるようにする。

**Independent Test**: `python scripts/update_gyousei_kuiki.py` 実行後、`ksj/data_collections/gyousei_kuiki.json` の内容が N03 ページの一覧と一致し、契約仕様（`specs/002-admin-area-data/contracts/data-collection-gyousei-kuiki.md`）を満たしていることを確認できる。

### Tests for User Story 1 (TDD)

- [x] T008 [US1] N03 ページの HTML から対象テーブル行を抽出し、「年度/地域/ファイル名」の生データリストに変換するユニットテストを `tests/test_update_gyousei_kuiki.py` に追加する
- [x] T009 [US1] 表示年度（例: `2025年（令和7年）`）から `YYYY年` 形式への正規化と、地域名の既存コレクション表記への正規化ロジックを検証するユニットテストを `tests/test_update_gyousei_kuiki.py` に追加する
- [x] T010 [US1] 同一年・同一地域に SHP/GML の複数候補がある場合に SHP 優先・無ければ GML を選択するロジックと、最終的な JSON 構造（年度 → 地域 → ファイル名）が期待どおりになることを検証するユニットテストを `tests/test_update_gyousei_kuiki.py` に追加する
- [x] T011 [US1] ネットワークエラー・テーブル未検出・書き込み失敗時に、それぞれ終了コード 1/2/3 を返すことを検証するユニットテストを `tests/test_update_gyousei_kuiki.py` に追加する

### Implementation for User Story 1

- [x] T012 [US1] エントリポイントと引数パース（対象 URL, 出力パス等）を備えた CLI スケルトンを `scripts/update_gyousei_kuiki.py` に実装する
- [x] T013 [US1] `urllib.request` と `html.parser.HTMLParser` を用いて N03 ページの HTML を取得し、契約どおりの対象テーブル（地域/年/ファイル名列を持つ `tbody`）を検出する処理を `scripts/update_gyousei_kuiki.py` に実装する
- [x] T014 [US1] テーブル行から年度・地域・ファイル名を抽出し、正規化前のレコードリストを `{year_display, region_raw, filename}` 形式で構築する処理を `scripts/update_gyousei_kuiki.py` に実装する
- [x] T015 [US1] 年度表示と地域名を正規化し、同一年・同一地域での複数候補から SHP/GML を選択して `{year: {region: filename}}` 構造の辞書を構築する処理を `scripts/update_gyousei_kuiki.py` に実装する
- [x] T016 [US1] 生成した辞書を UTF-8 の JSON として `ksj/data_collections/gyousei_kuiki.json` に上書き保存する処理を `scripts/update_gyousei_kuiki.py` に実装する
- [x] T017 [US1] ネットワーク/パース/書き込みの各失敗ケースで適切なログメッセージを出力し、契約どおりの終了コード 1/2/3 を返すよう `scripts/update_gyousei_kuiki.py` のメイン処理を実装する
- [x] T018 [US1] 実際に `python scripts/update_gyousei_kuiki.py` を実行し、生成された `ksj/data_collections/gyousei_kuiki.json` が `specs/002-admin-area-data/contracts/data-collection-gyousei-kuiki.md` の構造とサンプルに従っていることを手動確認する

**Checkpoint**: `update_gyousei_kuiki.py` のテストがすべてグリーンであり、`gyousei_kuiki.json` を再生成しても既存機能に影響を与えないことを確認できる。

---

## Phase 4: User Story 2 - ブラウザパネルでの行政区域データの表示 (Priority: P2)

**Goal**: QGIS ブラウザパネルで、既存の土砂災害警戒区域と同様に「行政区域」コレクションを表示し、年度・地域を選択して N03 データの GML をマップキャンバスに読み込めるようにする。

**Independent Test**: QGIS でブラウザパネルを開き、「国土数値情報（KSJ）」→「行政区域」→ 年度 → 地域を選択すると、対応する N03 リモート ZIP から GML が読み込まれ、マップキャンバスに描画されることを確認できる。

### Tests for User Story 2

- [x] T019 [US2] `load_data_collections()` が `ksj/data_collections/gyousei_kuiki.json` を読み込み、既存コレクションと同じ構造で辞書に格納することを検証するテストを `tests/test_data_loader.py` に追加する
- [x] T020 [US2] `get_data_collection_name()` が `gyousei_kuiki` に対して「行政区域」を返すことを検証するテストを `tests/test_data_loader.py` に追加する
- [x] T021 [US2] N03 のサンプル年度/ファイル名に対して `build_download_url()` が `https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-YYYY/<filename>` 形式の URL を生成することを検証するテストを `tests/test_data_loader.py` に追加する
- [x] T022 [US2] 「行政区域」コレクションの年度・地域ツリーが `gyousei_kuiki.json` から構築される設計であることを確認する（`ksj/browser.py` が `load_data_collections()` の内容を走査しているため追加実装不要、検証は T028 の手動確認で担保）
- [x] T023 [US2] 行政区域ノード展開/読み込み経路が `zip_scanner.py`（`.gml` 対応済み）に到達する設計であることを確認する（自動テストは `tests/test_data_loader.py` / `tests/test_zip_scanner.py` で担保、最終動作は T028 の手動確認で担保）

### Implementation for User Story 2

- [x] T024 [US2] `ksj/data_loader.py` の `get_data_collection_name()` に `"gyousei_kuiki": "行政区域"` のマッピングを追加する
- [x] T025 [US2] `ksj/browser.py` の KSJ ルート項目生成処理に `gyousei_kuiki` コレクションを組み込み、`load_data_collections()` の戻り値から行政区域コレクションをツリーに追加する（注: 既存の `KsjRootItem.createChildren()` が `load_data_collections()` を使用しているため、自動的に対応済み）
- [x] T026 [US2] `ksj/browser.py` 内で N03 行政区域ノードのダウンロード URL 生成に `build_download_url()` を使用し、年度キーとファイル名を `gyousei_kuiki.json` から取得するように接続する（注: 既存の `KsjPrefectureItem` が `build_download_url()` を使用しているため、自動的に対応済み）
- [x] T027 [US2] 行政区域ノードの展開/ダブルクリック時に `ksj/zip_scanner.py` を用いてリモート ZIP 内の `.gml` ファイルを列挙・読み込みする処理を `ksj/browser.py` に実装する（注: Phase 2 で `.gml` サポートを追加済み）
- [x] T028 [US2] QGIS 上でブラウザパネルを操作し、「行政区域」→ 任意の年度 → 地域を選択して `gyousei_kuiki.json` と `ksj/browser.py` のロジックに沿って正しいレイヤがマップキャンバスに表示されることを手動確認する（完了: 2026-01-11）

**Checkpoint**: ブラウザパネルから「行政区域」を選択して N03 データを読み込めることを自動テストと手動確認の両方で検証できる。

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: ドキュメント・クイックスタート・コード品質を整え、将来のコレクション追加や保守を容易にする。

- [x] T029 [P] 行政区域データの利用手順とテスト実行手順が最新になるように `specs/002-admin-area-data/quickstart.md` を更新する
- [x] T030 [P] プロジェクト全体の README とワークフロー説明（必要に応じて `README.md`, `WARP.md`）に行政区域サポートと `scripts/update_gyousei_kuiki.py` の概要を追記する
- [x] T031 行政区域関連の変更を含めて `pytest` でテストスイートをフル実行し、`tests/` 配下のすべてのテストがグリーンであることを確認する（macOS は `source setup_qgis_env.sh` を実行してから `pytest` を実行する）
- [x] T032 `scripts/update_gyousei_kuiki.py`, `ksj/data_loader.py`, `ksj/zip_scanner.py` の型ヒント・エラーメッセージ・命名を見直し、既存コードスタイルに合わせてリファクタリングする

**Checkpoint**: コードとドキュメントの整合性が取れ、他の開発者がこの機能の追加/更新を容易に引き継げる状態になっている。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 依存なし。最初に実行し、現状のテストが通ることを確認する。
- **Foundational (Phase 2)**: Setup 完了後に着手。URL 生成と ZIP スキャンの基盤が安定するまでユーザーストーリーの実装は行わない。
- **User Story 1 (Phase 3, P1)**: Phase 2 完了後に着手可能。ツールはブラウザ UI に依存しないため、US2 とは独立して実装・テストできる。
- **User Story 2 (Phase 4, P2)**: Phase 2 完了と、少なくとも `gyousei_kuiki.json` の基本生成が行える状態（US1 実装）が前提となる。US1 のツールを優先する（MVP）。
- **Polish (Phase 5)**: 主要なユーザーストーリー（US1, US2）が完了した後にまとめて実施する。

### User Story Dependencies

- **User Story 1 (P1)**: Foundational フェーズに依存するが、ブラウザ UI には依存しない。`scripts/update_gyousei_kuiki.py` と `gyousei_kuiki.json` の生成に集中できる。
- **User Story 2 (P2)**: Foundational フェーズと、`gyousei_kuiki.json` の存在に依存する。US1 ツールから生成された定義ファイルを前提にブラウザ表示と読み込みを実装する。

### Within Each User Story

- US1: `tests/test_update_gyousei_kuiki.py` のテスト（T008–T011）を先に書き、失敗を確認した上で `scripts/update_gyousei_kuiki.py` 実装（T012–T017）を行う。その後、実行確認（T018）を行う。
- US2: `tests/test_data_loader.py` と `tests/test_browser_items.py` のテスト（T019–T023）を追加し、`ksj/data_loader.py` と `ksj/browser.py` 実装（T024–T027）を進める。最後に QGIS 上での手動確認（T028）を行う。

---

## Parallel Opportunities

- Phase 1 完了後、Phase 2 のタスクのうちテスト追加（T004, T005, T007）と実装（T003, T006）は、ファイル衝突が起きない範囲で分担可能。
- Phase 3 と Phase 4 は共通基盤が整った後であれば、別の開発者が担当して並行作業することができる（US1 は CLI ツール、US2 は QGIS ブラウザ UI）。
- Polish フェーズでは、ドキュメント更新（T029, T030）とコードクリーンアップ（T032）は独立して進められる。

### Parallel Example: User Story 1

- テスト担当者: T008–T011 で `tests/test_update_gyousei_kuiki.py` のテストを拡充
- 実装担当者: T012–T017 で `scripts/update_gyousei_kuiki.py` の実装を並行して進め、テストが通るよう順次調整

### Parallel Example: User Story 2

- テスト担当者: T019–T023 で `tests/test_data_loader.py`, `tests/test_browser_items.py` のテストを追加
- 実装担当者: T024–T027 で `ksj/data_loader.py` と `ksj/browser.py` の実装・結合を進め、最後に T028 で手動確認

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1（Setup）で現行テストがグリーンであることを確認する（T001–T002）
2. Phase 2（Foundational）で URL 生成と ZIP スキャンの基盤を整える（T003–T007）
3. Phase 3（US1）で `update_gyousei_kuiki.py` による定義ファイル自動生成を実装し、テストと手動確認を完了する（T008–T018）
4. **STOP and VALIDATE**: `gyousei_kuiki.json` をコミット可能な状態にし、今後の更新もツール実行のみで対応できることを確認する

### Incremental Delivery

1. Setup + Foundational 完了 → 既存コレクションの回帰を確認
2. US1 完了 → データ定義の自動更新が可能になった時点で、必要であればここで小さなリリース/タグを切る
3. US2 完了 → ブラウザパネルから行政区域を利用可能にし、エンドユーザー向けにリリース
4. Polish 完了 → ドキュメントとコード品質を整えた状態で最終リリース

### Parallel Team Strategy

1. チーム全員で Phase 1–2 を短期間で完了させ、基盤を安定させる
2. その後、
   - 開発者 A: US1（Phase 3）担当 – `scripts/update_gyousei_kuiki.py` と `gyousei_kuiki.json`
   - 開発者 B: US2（Phase 4）担当 – `ksj/data_loader.py`, `ksj/browser.py`, `ksj/zip_scanner.py`
3. 最後に Polish フェーズ（Phase 5）でドキュメントとリファクタリングを共同で仕上げる
