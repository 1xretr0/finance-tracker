# TDD Evidence: Drop per-bank last-run files (derive cursor from DB)

**Source plan**: `~/.claude/plans/i-m-improving-the-banks-sunny-oasis.md` (Phase 1 only; Phase 2 "Sync now" dashboard button is deferred, per plan)

## User journeys
- As the person running `process_transactions` from any machine, I want the Gmail fetch cursor to come from the data itself, so I never have to commit/push a `*_last_run.txt` file to keep machines in sync.
- As that same person running in remote mode, I want the cursor read from the hosted DB (via `/api/status`) so the client and server never disagree about what's already been ingested.
- As a maintainer, I want a run that can't reach the configured remote server to abort cleanly instead of silently refetching everything or failing partway through a save.
- As a maintainer, I want to not lose transactions when more than `GMAIL_MAX_RESULTS` (250) new emails exist since the last run.

## Task report

| Task | Summary | Validation run | Result |
|---|---|---|---|
| Storage: `get_latest_tx_date` + `get_status()['latest_tx_dates']` | Added a query for the newest transaction date per source's bank list, excluding manual (`MAN-%`) rows; wired it into `get_status()` keyed by `SOURCE_BANKS` | `pytest tests/test_storage.py -q` | RED (ImportError) → GREEN (93 passed) |
| Constants: `SOURCE_BANKS`, `SYNC_OVERLAP_HOURS`; removed `SANTANDER_LAST_RUN_*` | Source→banks map + 48h overlap constant; file-path constants deleted | covered transitively by storage/santander/process_transactions suites | GREEN |
| Santander fetcher: stateless + paginated | `fetch_transactions(since_epoch=None)` replaces the file-based `_get_last_run_date`/`save_last_run_date`; follows `nextPageToken` instead of trusting a single page of `GMAIL_MAX_RESULTS` | `pytest tests/test_santander_fetch.py -q` | RED (ImportError) → GREEN (6 passed) |
| Orchestrator: `_compute_since`, `get_latest_date`, `run_sync` | Derives the epoch cursor from the latest stored date minus the overlap window; reads that date locally or via `/api/status` in remote mode; `run_sync` is the reusable core `main()` now calls (and that Phase 2's dashboard button will call) | `pytest tests/test_process_transactions.py -q` | RED (ImportError) → GREEN (24 passed) |
| Repo hygiene | Untracked + deleted `backend/banks/santander_last_run.txt`; dropped the dead `*_last_run.txt` `.gitignore` pattern; updated `CLAUDE.md` | `pytest tests/ -q` after removal | GREEN (320 passed) |

## Test specification

| # | What is guaranteed | Test file | Type | Result |
|---|---|---|---|---|
| 1 | `get_latest_tx_date` returns `None` on an empty DB | `tests/test_storage.py::TestGetLatestTxDate::test_returns_none_for_empty_db` | unit | PASS |
| 2 | Returns the max date among transactions for the given bank(s) | `tests/test_storage.py::TestGetLatestTxDate::test_returns_max_date_for_single_bank`, `test_returns_max_date_across_multiple_banks` | unit | PASS |
| 3 | Banks not in the list, and manually-created transactions, don't affect the result | `tests/test_storage.py::TestGetLatestTxDate::test_ignores_banks_not_in_list`, `test_excludes_manual_transactions` | unit | PASS |
| 4 | `get_status()` includes `latest_tx_dates` keyed by source | `tests/test_storage.py::TestGetLatestTxDate::test_includes_latest_tx_dates_in_status`, `test_latest_tx_dates_source_is_none_when_no_data` | unit | PASS |
| 5 | `fetch_transactions` omits `after:` when `since_epoch` is `None`/absent, includes it otherwise | `tests/test_santander_fetch.py::TestSinceEpochQuery` (3 tests) | unit | PASS |
| 6 | `fetch_transactions` follows `nextPageToken` across pages and stops when absent | `tests/test_santander_fetch.py::TestPagination` (3 tests) | unit | PASS |
| 7 | `_compute_since` returns `None` for no prior data, otherwise subtracts `SYNC_OVERLAP_HOURS` | `tests/test_process_transactions.py::TestComputeSince` (3 tests) | unit | PASS |
| 8 | `get_latest_date` reads from `/api/status` in remote mode (with bearer auth) and raises on an unreachable server; reads from storage locally | `tests/test_process_transactions.py::TestGetLatestDate` (3 tests) | unit | PASS |
| 9 | `run_sync` fetches with the derived cursor and routes to insert (local) or push (remote); aborts with zero counts (no fetch) if the cursor lookup fails; returns zero counts if nothing was fetched | `tests/test_process_transactions.py::TestRunSync` (4 tests) | unit/integration | PASS |
| 10 | `main()`'s existing remote/local routing and logging behavior is preserved under the new cursor plumbing | `tests/test_process_transactions.py::TestMainUsesRemoteSinkWhenConfigured` (3 tests, updated) | integration | PASS |
| 11 | `/api/status` endpoint still returns 200 with auth, 401 without | `tests/test_server.py::TestStatusEndpoint` (pre-existing, unmodified) | integration | PASS |

## Coverage and known gaps
- No coverage tool is wired into this project (`pytest-cov` isn't in `requirements.txt`); coverage is reported qualitatively above — every new/changed function (`get_latest_tx_date`, the `get_status` extension, `fetch_transactions`'s pagination/cursor branches, `_compute_since`, `get_latest_date`, `run_sync`) has at least one direct unit test, plus `main()`'s existing integration tests continue to exercise the call chain end-to-end.
- `pytest tests/ -q` → **320 passed**, 0 failed, 0 skipped (run after every GREEN checkpoint below).
- **Not covered by this change (deferred, per plan Phase 2)**: the dashboard "Sync now" button / `POST /api/sync` endpoint, and running Gmail ingestion from the PythonAnywhere host.
- **Not covered by tests, verify manually**: an actual Gmail account with >250 pending messages (pagination logic is unit-tested against a fake multi-page service, not the real API).

## Checkpoint commits (RED/GREEN per task, on `last-run-date-sync`)
1. `b77d856` test (RED): `get_latest_tx_date` reproducer
2. `c9c91a1` fix (GREEN): storage layer implementation — 93 passed
3. `8d574bc` test (RED): stateless/paginated Santander fetch reproducer
4. `4ec2878` test (RED, includes GREEN santander.py impl bundled with the next RED): orchestrator-level reproducers for `_compute_since`/`get_latest_date`/`run_sync`
5. `2b7f981` fix (GREEN): `process_transactions.py` orchestrator — 320 passed
6. `1fda5e9` chore: retire the file, `.gitignore` entry, and docs — 320 passed (final state)
