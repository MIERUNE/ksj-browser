---
description: 'Task list for Zip 再帰探索ブラウズ'
---

# Tasks: Zip 再帰探索ブラウズ

**Input**: Design documents from `/specs/001-zip-recursive-browse/`

- `specs/001-zip-recursive-browse/spec.md`
- `specs/001-zip-recursive-browse/plan.md`
- `specs/001-zip-recursive-browse/research.md`
- `specs/001-zip-recursive-browse/data-model.md`
- `specs/001-zip-recursive-browse/contracts/remote-zip.md`
- `specs/001-zip-recursive-browse/contracts/browser-items.md`
- `specs/001-zip-recursive-browse/quickstart.md`

**Notes**

- 憲法によりテストファースト（テスト作成 → ユーザー承認 → テスト失敗 → 実装 → テスト成功）は必須とする。
- ネットワーク依存は不安定要因のため、デフォルトはモック/小さなローカル ZIP でユニットテストを行う。KSJ サイトへの実アクセスは任意の統合テストとして切り分ける。

## Format

- すべてのタスクは次の形式に統一する:
  - `- [ ] T### [P?] [US?] 説明 ... (file path)`
- `[P]` は「別ファイルで独立に進められる」場合のみ付ける
- `[US#]` はユーザーストーリーのフェーズ内タスクのみ付ける

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 実装前の前提合わせ（仕様/契約/入力データを確定し、後続の手戻りを避ける）

- [x] T001 仕様と契約の整合を最終確認する（specs/001-zip-recursive-browse/spec.md, specs/001-zip-recursive-browse/contracts/remote-zip.md, specs/001-zip-recursive-browse/contracts/browser-items.md）
- [x] T002 受入テスト入力（年度 × 都道府県 ×ZIP 名）の代表例を 1 つ決めてメモする（ksj/data_collections/dosyasaigai_keikai_kuiki.json, specs/001-zip-recursive-browse/spec.md）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 全ユーザーストーリーで共通利用する「リモート ZIP 走査」基盤を用意する（ブラウザ表示・追加はこの後）

- [x] T003 リモート ZIP 走査モジュールの公開 API（関数名/戻り値/例外/正規化ルール）を確定し、契約と一致させる（ksj/zip_scanner.py, specs/001-zip-recursive-browse/contracts/remote-zip.md）
- [x] T004 テスト（まず失敗させる）: ZIP 再帰列挙・フィルタ・ツリー化・同名識別・例外伝播のユニットテストを追加する（tests/test_zip_scanner.py）
- [x] T005 ユーザー承認: T004 のテスト内容をレビュー依頼し、承認を得る（specs/001-zip-recursive-browse/tasks.md）
- [x] T006 リモート ZIP 走査モジュールの骨組みを追加する（ksj/zip_scanner.py）
- [x] T007 リモート ZIP の再帰列挙を GDAL VSI で実装する（/vsizip//vsicurl + gdal.ReadDir）（ksj/zip_scanner.py）
- [x] T008 走査結果から `.shp` / `.geojson` のみを抽出するフィルタを実装する（ksj/zip_scanner.py）
- [x] T009 同名ファイルでも識別できるよう、ZIP 内パスから表示名を生成するルールを実装する（例: `folder1/file.shp`）（ksj/zip_scanner.py）
- [x] T010 ZIP 内パス一覧からフォルダ階層ツリーを組み立てるヘルパを実装する（ZipNode 相当）（ksj/zip_scanner.py）
- [x] T011 走査失敗（403/404/タイムアウト/破損 ZIP）を上位へ伝播できる例外型とユーザー向けメッセージ整形を実装する（ksj/zip_scanner.py）
- [x] T012 テストを成功させる（T004 がパスすることを確認する）（tests/test_zip_scanner.py）
- [x] T013 [P] 回帰テスト: ダウンロード URL 生成が壊れていないことを確認するテストを追加する（tests/test_data_loader.py）

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - リモート ZIP 内データの一覧表示 (Priority: P1) 🎯 MVP

**Goal**: リモート ZIP の内部構造に依存せず、ZIP 内の `.geojson` / `.shp` をブラウザに（階層付きで）表示できる

**Independent Test**: QGIS ブラウザで任意の都道府県ノードを展開し、ZIP 内に存在する `.geojson` / `.shp` がツリー上に表示される（ネットワークエラー時はクラッシュせず、ユーザー向けメッセージが出る）

### Tests for User Story 1

- [x] T014 [US1] テスト（まず失敗させる）: ZIP 内ツリー生成の入力（ZipNode ツリー）をモックで与え、ブラウザ子要素生成が期待どおりになることをテストする（tests/test_browser_items.py）
- [x] T015 [US1] ユーザー承認: T014 のテスト内容をレビュー依頼し、承認を得る（specs/001-zip-recursive-browse/tasks.md）

- [x] T016 [US1] 都道府県ノード展開時にリモート ZIP を走査し、ZIP 内ツリーの子要素を生成する処理を追加する（ksj/browser.py）
- [x] T017 [US1] ZIP 内フォルダを表すコレクションアイテムを追加する（ksj/browser.py）
- [x] T018 [US1] ZIP 内ファイル（`.shp` / `.geojson`）を表すデータアイテムを追加する（ksj/browser.py）
- [x] T019 [US1] ZIP に対象ファイルが無い場合に「対象データなし」を示す子要素（または情報アイテム）を表示する（ksj/browser.py）
- [x] T020 [US1] 走査失敗時にクラッシュせず、ユーザー向けメッセージが表示されるようにする（表示経路を統一する）（ksj/browser.py）
- [x] T021 [US1] テストを成功させる（T014 がパスすることを確認する）（tests/test_browser_items.py）

**Checkpoint**: User Story 1 should be functional and independently verifiable

---

## Phase 4: User Story 2 - 都道府県単位での整理 (Priority: P2)

**Goal**: 都道府県ノードを `QgsDataCollectionItem` として扱い、配下に ZIP 内フォルダ/ファイルを自然にぶら下げられる

**Independent Test**: 年度 → 都道府県ノードが「展開可能（フォルダ扱い）」として振る舞い、配下に ZIP 内のフォルダ/ファイルが表示される

- [ ] T022 [US2] 都道府県ノードを `QgsDataCollectionItem` ベースのクラスに置換し、年度ノードから生成するように変更する（ksj/browser.py）
- [ ] T023 [US2] 都道府県ノードの表示名を維持しつつ、ZIP 内ツリー生成の責務を都道府県ノード側に寄せる（ksj/browser.py）

**Checkpoint**: User Story 2 should be functional and independently verifiable

---

## Phase 5: User Story 3 - ダブルクリックで地図へ追加 (Priority: P3)

**Goal**: ZIP 内の `.geojson` / `.shp` 項目をダブルクリック（および DnD）で QGIS にレイヤとして追加できる

**Independent Test**: ブラウザ上の `.geojson` / `.shp` をダブルクリックし、QGIS のレイヤに追加される（失敗時は理由が分かる）

- [ ] T024 [US3] テスト（まず失敗させる）: ファイル項目が生成する URI（provider `ogr` と `/vsizip//vsicurl/.../<path-in-zip>`）の期待値をテストする（tests/test_browser_layer_add.py）
- [ ] T025 [US3] ユーザー承認: T024 のテスト内容をレビュー依頼し、承認を得る（specs/001-zip-recursive-browse/tasks.md）
- [ ] T026 [US3] ZIP 内ファイル項目の DnD 用 URI（`/vsizip//vsicurl/<url>/<path-in-zip>` + provider `ogr`）を返すようにする（ksj/browser.py）
- [ ] T027 [US3] ZIP 内ファイル項目のダブルクリックで `QgsVectorLayer` を作成して `QgsProject` に追加する（ksj/browser.py）
- [ ] T028 [US3] `.shp` の関連ファイル不足などで追加に失敗した場合、失敗理由が分かるメッセージを表示する（ksj/browser.py）
- [ ] T029 [US3] テストを成功させる（T024 がパスすることを確認する）（tests/test_browser_layer_add.py）

**Checkpoint**: User Story 3 should be functional and independently verifiable

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 仕上げ、不要コード除去、ドキュメント整合

- [ ] T030 旧固定パス前提の関数を削除または用途を限定し、参照が残っていないことを確認する（ksj/data_loader.py, ksj/browser.py）
- [ ] T031 [P] Quickstart の手順が現状実装と矛盾しないように更新する（specs/001-zip-recursive-browse/quickstart.md）
- [ ] T032 [P] 仕様（成功基準/エッジケース）と実装の挙動が一致するように最終確認メモを追記する（specs/001-zip-recursive-browse/spec.md）

---

## Dependencies & Execution Order

### User Story Dependencies

- User Story 1 (P1) blocks User Story 2/3（ZIP 内ファイルの列挙・表示が前提）
- User Story 2 (P2) improves structure of the same UI surface; should be done before finalizing US3 UX
- User Story 3 (P3) depends on having file items from US1 (and is simplest after US2 refactor)

**Suggested order**: Phase 1 → Phase 2 → US1 → US2 → US3 → Polish

---

## Parallel Opportunities

- Phase 6: `T020` と `T021` は別ファイルで並行可能

---

## Parallel Example: User Story 1

- 現状、US1 の主要タスクは同一ファイル（ksj/browser.py）への変更が集中するため、大きな並行分割は推奨しない
- 並行するなら、走査ロジック（ksj/zip_scanner.py）完成後に UI 反映（ksj/browser.py）へ進む

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 + Phase 2 を完了
2. Phase 3 (US1) を完了
3. QGIS ブラウザで表示確認（ネットワークエラー時もクラッシュしないこと）
4. ここで一旦止めて検証し、OK なら US2/US3 を進める
