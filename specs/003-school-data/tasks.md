---
description: 'Task list for school data (P29) support feature'
---

# Tasks: 学校データのサポート追加

**Input**: Design documents from `/specs/003-school-data/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)

**Tests**: Tests are included for all new functionality following the Test-First Development principle from the constitution.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `- [ ] [ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization - ensure development environment is ready

- [x] T001 Verify QGIS 3.28+ and Python 3.9+ environment
- [x] T002 Verify uv package manager is installed
- [x] T003 Create virtual environment with `uv venv --python /Applications/QGIS.app/Contents/MacOS/bin/python3 --system-site-packages`
- [x] T004 Verify pytest and pytest-qgis are available in environment

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 [P] Create HTML fixture file `tests/fixtures/p29_sample.html` with sample P29 table data
- [x] T006 [P] Verify existing utility functions in `scripts/update_gyousei_kuiki.py` for reference

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - データ更新ツールの実行 (Priority: P1) 🎯 MVP

**Goal**: 開発者が学校データの最新版を国土数値情報 Web サイトから自動取得してデータコレクション定義ファイルを更新できる

**Independent Test**: `python scripts/update_gakkou.py` を実行し、`ksj/data_collections/gakkou.json` が生成され、Web サイトと同じ内容（年度・地域・ファイル名）が含まれることを確認

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T007 [P] [US1] Create test file `tests/test_update_gakkou.py` with test structure and imports
- [x] T008 [P] [US1] Write test `test_normalize_year()` to verify year normalization (e.g., `2023年（令和5年）` → `2023年`)
- [x] T009 [P] [US1] Write test `test_normalize_region()` to verify region normalization (e.g., `青森県` → `青森`)
- [x] T010 [P] [US1] Write test `test_extract_table_rows()` using `tests/fixtures/p29_sample.html` to verify HTML parsing
- [x] T011 [P] [US1] Write test `test_deduplicate_by_format()` to verify SHP priority over GML
- [x] T012 [P] [US1] Write test `test_main_success()` to verify full workflow with mocked HTTP request
- [x] T013 [P] [US1] Write test `test_main_network_error()` to verify exit code 1 on network failure
- [x] T014 [P] [US1] Write test `test_main_parse_error()` to verify exit code 2 on HTML parse failure

### Implementation for User Story 1

- [x] T015 [US1] Create `scripts/update_gakkou.py` with CLI structure using argparse (--url, --output options)
- [x] T016 [P] [US1] Implement `normalize_year(year_display: str) -> str` function in `scripts/update_gakkou.py`
- [x] T017 [P] [US1] Implement `normalize_region(region_raw: str) -> str` function in `scripts/update_gakkou.py`
- [x] T018 [P] [US1] Implement `extract_table_rows(html_content: str) -> list[dict]` function using html.parser
- [x] T019 [P] [US1] Implement `deduplicate_by_format(rows: list[dict]) -> list[dict]` function (SHP priority)
- [x] T020 [US1] Implement `group_by_year_region(rows: list[dict]) -> dict` function to create nested structure
- [x] T021 [US1] Implement `main()` function with error handling and exit codes (0, 1, 2, 3)
- [x] T022 [US1] Run tests: `source setup_qgis_env.sh && uv run python -m pytest tests/test_update_gakkou.py -v`
- [x] T023 [US1] Fix any failing tests and ensure all tests pass
- [x] T024 [US1] Execute tool: `python scripts/update_gakkou.py` to generate `ksj/data_collections/gakkou.json`
- [x] T025 [US1] Verify generated JSON structure matches contract in `contracts/data-collection.md`
- [x] T026 [US1] Validate JSON with `cat ksj/data_collections/gakkou.json | jq .`

**Checkpoint**: At this point, User Story 1 should be fully functional - the update tool generates valid gakkou.json

---

## Phase 4: User Story 2 - ブラウザパネルでの学校データの表示 (Priority: P2)

**Goal**: QGIS ユーザーがブラウザパネルで学校データをツリー構造で表示し、選択してデータを読み込めるようにする

**Independent Test**: QGIS でブラウザパネルを開き、「国土数値情報（KSJ）」→「学校」が表示され、年度と地域を展開してダブルクリックでデータを読み込めることを確認

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T027 [P] [US2] Add test `test_load_gakkou_collection()` to `tests/test_data_loader.py` to verify gakkou.json is loaded
- [x] T028 [P] [US2] Add test `test_get_gakkou_collection_name()` to `tests/test_data_loader.py` to verify display name is "学校"
- [x] T029 [P] [US2] Add test `test_build_gakkou_download_url()` to `tests/test_data_loader.py` to verify URL generation for P29

### Implementation for User Story 2

- [x] T030 [US2] Add `"gakkou": "学校"` to `_COLLECTION_NAMES` dictionary in `ksj/data_loader.py`
- [x] T031 [US2] Add `"P29": _get_dir_year_from_filename_yy` to `_DIR_YEAR_STRATEGIES` dictionary in `ksj/data_loader.py`
- [x] T032 [US2] Run tests: `source setup_qgis_env.sh && uv run python -m pytest tests/test_data_loader.py -v`
- [x] T033 [US2] Fix any failing tests and ensure all tests pass
- [x] T034 [US2] Verify no regressions: `source setup_qgis_env.sh && uv run python -m pytest -v`

**Checkpoint**: At this point, User Stories 1 AND 2 should both work - gakkou.json is generated and can be loaded by the plugin

---

## Phase 5: Integration & Manual Verification

**Purpose**: Verify end-to-end functionality in actual QGIS environment

- [ ] T035 Start QGIS application
- [ ] T036 Reload plugin using Plugin Reloader
- [ ] T037 Open Browser Panel (View → Panels → Browser)
- [ ] T038 Expand "国土数値情報（KSJ）" node
- [ ] T039 Verify "学校" appears alongside "土砂災害警戒区域" and "行政区域"
- [ ] T040 Expand "学校" → Select a year (e.g., "2023 年")
- [ ] T041 Verify region list appears (e.g., 北海道, 青森, etc.)
- [ ] T042 Double-click a region (e.g., "北海道") to load data onto map canvas
- [ ] T043 Verify school data (P29) loads and displays correctly on map

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, cleanup, and final quality checks

- [x] T044 [P] Update `README.md` to add "学校（P29）" to the supported collections list
- [x] T045 [P] Update `README.md` project structure section to include `scripts/update_gakkou.py` and `tests/test_update_gakkou.py`
- [x] T046 [P] Add documentation comment to `scripts/update_gakkou.py` describing purpose and usage
- [x] T047 Run full test suite with coverage: `.venv/bin/pytest tests/ --cov=ksj --cov=scripts --cov-report=term-missing`
- [x] T048 Verify coverage for new code is ≥80%
- [x] T049 Run linter: `uv run ruff check .`
- [x] T050 Fix any linting issues
- [x] T051 Review and validate against `specs/003-school-data/quickstart.md` workflow
- [x] T052 Commit changes: `git add ksj/data_collections/gakkou.json scripts/update_gakkou.py tests/test_update_gakkou.py ksj/data_loader.py tests/test_data_loader.py`
- [x] T053 Create commit with message: `feat: Add support for school data (P29)`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup (Phase 1) completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2) completion
- **User Story 2 (Phase 4)**: Depends on User Story 1 (Phase 3) completion - requires gakkou.json to exist
- **Integration (Phase 5)**: Depends on User Story 2 (Phase 4) completion
- **Polish (Phase 6)**: Depends on all user stories and integration being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Depends on User Story 1 - requires `gakkou.json` file to exist

### Within Each User Story

1. Tests MUST be written FIRST and FAIL before implementation (TDD)
2. Implementation tasks follow test tasks
3. Verification and validation tasks follow implementation
4. Story must be independently testable before moving to next priority

### Parallel Opportunities Within User Story 1

```bash
# Phase 2: Foundational tasks
T005 [P] Create HTML fixture file
T006 [P] Verify existing utility functions

# Phase 3: User Story 1 - All test tasks can run in parallel:
T008 [P] test_normalize_year()
T009 [P] test_normalize_region()
T010 [P] test_extract_table_rows()
T011 [P] test_deduplicate_by_format()
T012 [P] test_main_success()
T013 [P] test_main_network_error()
T014 [P] test_main_parse_error()

# Phase 3: User Story 1 - Some implementation tasks can run in parallel:
T016 [P] normalize_year()
T017 [P] normalize_region()
T018 [P] extract_table_rows()
T019 [P] deduplicate_by_format()
```

### Parallel Opportunities Within User Story 2

```bash
# Phase 4: User Story 2 - All test tasks can run in parallel:
T027 [P] test_load_gakkou_collection()
T028 [P] test_get_gakkou_collection_name()
T029 [P] test_build_gakkou_download_url()
```

### Parallel Opportunities Within Polish Phase

```bash
# Phase 6: Polish - Documentation tasks can run in parallel:
T044 [P] Update README.md collections list
T045 [P] Update README.md project structure
T046 [P] Add documentation to update_gakkou.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T006) - CRITICAL
3. Complete Phase 3: User Story 1 (T007-T026)
4. **STOP and VALIDATE**: Run `python scripts/update_gakkou.py` and verify `gakkou.json` generation
5. At this point, MVP is complete - developers can automatically update school data

### Incremental Delivery

1. **Foundation**: Setup (Phase 1) + Foundational (Phase 2) → T001-T006
2. **MVP**: User Story 1 (Phase 3) → T007-T026 → Test independently with `python scripts/update_gakkou.py`
3. **Full Feature**: User Story 2 (Phase 4) → T027-T034 → Test independently with pytest
4. **Integration**: Manual QGIS verification (Phase 5) → T035-T043 → Verify end-to-end workflow
5. **Production Ready**: Polish (Phase 6) → T044-T053 → Documentation and commit

### Sequential Team Strategy (Single Developer)

1. Complete phases in order: 1 → 2 → 3 → 4 → 5 → 6
2. Within each phase, complete tasks in sequence or use [P] markers for parallel work
3. Validate at each checkpoint before moving to next phase

### Parallel Team Strategy (Multiple Developers)

With 2 developers:

1. **Together**: Complete Phase 1 (Setup) and Phase 2 (Foundational)
2. **Developer A**: User Story 1 (Phase 3) - Data update tool
3. **Developer B**: Prepare test infrastructure for User Story 2 (wait for gakkou.json)
4. **Developer A**: Hands off gakkou.json to Developer B
5. **Developer B**: User Story 2 (Phase 4) - Browser integration
6. **Together**: Integration testing (Phase 5) and Polish (Phase 6)

---

## Implementation Notes

### Test-First Development

- All tests MUST be written before implementation (Constitution requirement)
- Tests MUST fail initially (prove they're testing the right thing)
- Implementation makes tests pass
- Run tests frequently: `source setup_qgis_env.sh && uv run python -m pytest -v`

### File Organization

- Scripts: `scripts/update_gakkou.py` (standalone tool)
- Tests: `tests/test_update_gakkou.py` (script tests), `tests/test_data_loader.py` (loader tests)
- Data: `ksj/data_collections/gakkou.json` (generated output, committed to repo)
- Fixtures: `tests/fixtures/p29_sample.html` (test data)

### Import Strategy

- `scripts/` uses absolute imports (standalone scripts)
- `ksj/` uses relative imports: `from . import data_loader` (Plugin Reloader compatibility)
- Tests use absolute imports: `from scripts.update_gakkou import normalize_year`

### Error Handling

Follow contract specifications in `contracts/update-tool.md`:

- Exit code 0: Success
- Exit code 1: Network error
- Exit code 2: HTML parse error
- Exit code 3: File write error

### Validation Commands

```bash
# Test execution (macOS)
source setup_qgis_env.sh && uv run python -m pytest -v

# Or direct execution
.venv/bin/pytest tests/ -v

# Coverage check
.venv/bin/pytest tests/ --cov=ksj --cov=scripts --cov-report=term-missing

# JSON validation
cat ksj/data_collections/gakkou.json | jq .

# Linting
uv run ruff check .
```

---

## Success Metrics

### Task Count Summary

- **Total Tasks**: 53
- **Setup**: 4 tasks (T001-T004)
- **Foundational**: 2 tasks (T005-T006)
- **User Story 1**: 20 tasks (T007-T026)
- **User Story 2**: 8 tasks (T027-T034)
- **Integration**: 9 tasks (T035-T043)
- **Polish**: 10 tasks (T044-T053)

### Parallel Opportunities

- **Phase 2 Foundational**: 2 tasks can run in parallel
- **Phase 3 US1 Tests**: 7 test tasks can run in parallel
- **Phase 3 US1 Implementation**: 4 implementation tasks can run in parallel
- **Phase 4 US2 Tests**: 3 test tasks can run in parallel
- **Phase 6 Polish**: 3 documentation tasks can run in parallel

### Independent Test Criteria

- **User Story 1**: Execute `python scripts/update_gakkou.py` → Verify `gakkou.json` contains correct data
- **User Story 2**: Run pytest → Verify data_loader tests pass → QGIS manual test confirms browser display

### MVP Scope

**Minimum Viable Product = User Story 1 (P1) Only**

- Tasks T001-T026 (26 tasks)
- Deliverable: Automated data update tool for P29 school data
- Value: Eliminates manual data definition updates
- Validation: `python scripts/update_gakkou.py` generates valid `gakkou.json`

### Format Validation

✅ **All tasks follow the checklist format**:

- All tasks start with `- [ ]` (markdown checkbox)
- All tasks have sequential IDs (T001, T002, T003...)
- Parallelizable tasks marked with `[P]`
- User story tasks marked with `[US1]` or `[US2]`
- All tasks include clear descriptions with file paths where applicable

---

## Notes

- [P] tasks = different files, no dependencies - can run in parallel
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD requirement)
- Commit after logical task groups (not after every single task)
- Stop at checkpoints to validate story independently
- Follow Constitution requirements: Test-First, Modular Design, Relative Imports
- macOS testing requires: `source setup_qgis_env.sh` before pytest
