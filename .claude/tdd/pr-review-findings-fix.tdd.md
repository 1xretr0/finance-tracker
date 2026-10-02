# TDD Evidence: Fix PR #2 review findings (silent failures, lost tracebacks, stray dependency, test gaps)

**Source**: `/review-pr #2` multi-agent review (code-reviewer, comment-analyzer, pr-test-analyzer, silent-failure-hunter, type-design-analyzer, code-simplifier) on branch `last-run-date-sync` — 4 findings rated Important, addressed here.

## User journeys
- As the person running `process_transactions` unattended (cron/launchd), I want a failed run (bad cursor, unreachable Gmail/remote API, failed save) to exit non-zero, so it doesn't look identical in logs to "nothing new to fetch."
- As the person debugging an intermittent failure, I want the full traceback in the log, not just `str(exception)`, so I don't have to reproduce locally to find where it broke.
- As a maintainer reading `requirements.txt`, I don't want an unrelated/no-op dependency (`db-sqlite3`, an npm-style stub unrelated to Python's stdlib `sqlite3`) sitting there unexplained.
- As a maintainer trusting the test suite, I want the untested failure paths (save-step exception, cursor-value correctness, multi-page parse failures) actually exercised, so a regression in any of them is caught.

## Task report

| Task | Summary | Validation run | Result |
|---|---|---|---|
| `run_sync` failure signal | Returns `None` on cursor/fetch/save failure instead of `dict(ZERO_RESULT)`, keeping the zero-count dict only for the legitimate "fetched successfully, nothing new" case | `pytest tests/test_process_transactions.py -v` | RED (5 failures) → GREEN |
| `main()` exit code | `sys.exit(1)` when `run_sync()` returns `None` | same | RED → GREEN |
| Traceback preservation | `logger.error(f"...: {e}")` → `logger.exception(...)` in all 3 except-blocks of `run_sync` | same (via `caplog`, asserts `record.exc_info is not None`) | RED → GREEN |
| `requirements.txt` cleanup | Removed the `db-sqlite3` line (preserving the file's existing UTF-16 encoding) | `pytest tests/ -q` | GREEN, no test needed (not executable logic) |
| Test gap: save-step failure | Added `test_returns_none_when_save_fails` | same | RED → GREEN |
| Test gap: fetch-step failure | Added `test_returns_none_when_fetch_fails` | same | RED → GREEN |
| Test gap: cursor-value correctness | Added `test_remote_mode_cursor_matches_compute_since`, asserting the exact epoch passed to `fetch_santander` equals `_compute_since`'s output (previously only `is not None` was checked) | same | Passed without code changes (confirms existing correctness; closes the gap) |
| Test gap: multi-page parse failure | Added `test_unparsable_message_is_skipped_and_later_pages_still_processed` in `test_santander_fetch.py` | `pytest tests/test_santander_fetch.py -v` | Passed without code changes (confirms existing pagination correctness; closes the gap) |

## Test specification

| # | What is guaranteed | Test | Result |
|---|---|---|---|
| 1 | `run_sync` returns `None` (not a zero-count dict) when the cursor lookup raises | `TestRunSync::test_aborts_without_fetching_when_cursor_lookup_fails` | PASS |
| 2 | `run_sync` returns `None` when `fetch_santander` raises, without attempting a save | `TestRunSync::test_returns_none_when_fetch_fails` | PASS |
| 3 | `run_sync` returns `None` when the save step raises | `TestRunSync::test_returns_none_when_save_fails` | PASS |
| 4 | `run_sync` still returns a zero-count dict (not `None`) when fetch succeeds but returns nothing | `TestRunSync::test_returns_zero_counts_when_nothing_fetched` | PASS |
| 5 | The epoch passed to `fetch_santander` matches `_compute_since`'s output for the derived latest date | `TestRunSync::test_remote_mode_cursor_matches_compute_since` | PASS |
| 6 | A cursor-lookup failure logs a record with a captured traceback (`exc_info`) | `TestRunSync::test_logs_traceback_on_cursor_failure` | PASS |
| 7 | `main()` exits with status 1 when `run_sync()` fails | `TestMainExitsOnFailure::test_main_exits_nonzero_when_sync_fails` | PASS |
| 8 | `main()` does not raise/exit when `run_sync()` succeeds | `TestMainExitsOnFailure::test_main_does_not_exit_when_sync_succeeds` | PASS |
| 9 | A message that fails to parse doesn't abort the fetch; later pages/messages are still processed | `TestPagination::test_unparsable_message_is_skipped_and_later_pages_still_processed` | PASS |

## Coverage and known gaps
- `pytest tests/ -q` → **327 passed**, 0 failed, 0 skipped (up from 320 before this round; 7 new tests added, 1 existing assertion updated).
- `requirements.txt`'s `db-sqlite3` removal has no test (it's dependency metadata, not executable logic) — verified by inspection and full suite still green.
- Not addressed here (out of scope for "fix the 4 Important findings"): the `SyncResult` TypedDict suggestion (Advisory, not requested), the `ZERO_RESULT`/`dict(ZERO_RESULT)` cosmetic simplification (Advisory), and `requirements.txt`'s underlying UTF-16 encoding (pre-existing, not flagged by reviewers as a finding, out of scope).

## Checkpoint commits (RED/GREEN, on `last-run-date-sync`)
1. `9a0b402` test (RED): reproducers for silent sync failures, lost tracebacks, and pagination parse-failure coverage — 5 of 37 tests failed for the intended reason, 32 passed (including the already-correct cursor-value and parse-failure tests, confirming those two were coverage gaps, not bugs)
2. `7cda5ea` fix (GREEN): `run_sync`/`main()` failure signaling, `logger.exception`, `requirements.txt` cleanup — 327 passed
