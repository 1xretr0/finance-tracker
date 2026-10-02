# TDD Evidence: "Sync now" dashboard button (Phase 2)

**Source plan**: `~/.claude/plans/i-m-improving-the-banks-sunny-oasis.md` (Phase 2 — depends on Phase 1's DB-derived cursor, see `.claude/tdd/db-derived-last-run-cursor.tdd.md`)

Implemented on branch `sync-now-dashboard`, in an isolated git worktree (`finance-tracker-sync-now`) created so this session's branch switch wouldn't disturb a peer session reviewing Phase 1's PR #2 in the main working directory.

## User journeys
- As the person hosting the dashboard on PythonAnywhere, I want a "Sync now" button that fetches new Santander transactions and stores them, so I don't need to run `process_transactions.py` from my laptop for a quick incremental sync.
- As that same host, I want a sync request to never hang waiting for an interactive OAuth browser flow — there's no browser on the server — so a missing/expired/unrefreshable token must fail fast with a clear "re-authenticate locally and upload token.json" error instead.
- As that same host, I want a second "Sync now" click while one is already running to be rejected (409) instead of racing the first sync, since PythonAnywhere's free tier has no reliable background workers.
- As the deployer, I want to upload only `token.json` (not the whole project layout assumption) to a configurable path, so the host doesn't need `credentials.json` or the ingestion script.

## Task report

| Task | Summary | Validation run | Result |
|---|---|---|---|
| `TOKEN_FILE` overridable via `TOKEN_PATH` | `backend/constants.py`: `TOKEN_FILE = os.environ.get("TOKEN_PATH", <default>)`, mirroring the existing `DB_PATH` pattern | `pytest tests/test_server.py::TestApiAuth -q` | RED (default-path assertion failed for the override case) → GREEN |
| `_authenticate(interactive)` + `AuthenticationRequiredError` | `backend/banks/santander.py`: `_authenticate(interactive=True)` only refreshes (never calls `InstalledAppFlow.run_local_server`) when `interactive=False`; raises `AuthenticationRequiredError` if no valid/refreshable token exists | `pytest tests/test_santander_auth.py -q` | RED (ImportError: `AuthenticationRequiredError` didn't exist) → GREEN (6 passed) |
| `fetch_transactions(since_epoch, interactive)` | Forwards `interactive` to `_authenticate` | `pytest tests/test_santander_fetch.py -q` | RED (`TypeError: unexpected keyword argument 'interactive'`) → GREEN (14 passed) |
| `run_sync(use_remote, interactive)` | Forwards `interactive` to `fetch_santander`; lets `AuthenticationRequiredError` propagate instead of being swallowed into the generic `except Exception` → zero-result branch, so the caller can distinguish it | `pytest tests/test_process_transactions.py::TestRunSync -q` | RED (ImportError / wrong call signature) → GREEN (7 passed) |
| `POST /api/sync` | New Flask route behind existing bearer auth; non-blocking `threading.Lock` (409 if already running, released via `finally` even on error); lazily imports `run_sync`/`AuthenticationRequiredError`; maps that exception to 503 | `pytest tests/test_server.py::TestSyncEndpoint -q` | RED (`NameError`/`AttributeError`/`ImportError`) → GREEN (6 passed) |
| "Sync now" button | `frontend/js/common.js`: `initHeaderChrome()` inserts a button next to `#sync-status`; `triggerSync()` calls `apiFetch("/api/sync", {method: "POST"})`, disables the button while in flight, shows the error or inserted count, reloads on success. `frontend/css/styles.css`: `.btn-sync-now` matching the existing `.btn-logout` dark-mode style. | Manual only — no JS test runner in this repo (pytest only) | Not automated; see gap below |

## Test specification

| # | What is guaranteed | Test file | Type | Result |
|---|---|---|---|---|
| 1 | `TOKEN_FILE` defaults to `<project_root>/token.json` when `TOKEN_PATH` is unset, and equals `TOKEN_PATH` verbatim when set | `tests/test_server.py::TestApiAuth::test_token_file_defaults_to_project_root`, `test_token_file_overridable_via_env` | unit | PASS |
| 2 | `_authenticate(interactive=True)` runs the interactive flow when no token exists | `tests/test_santander_auth.py::TestInteractiveAuthentication::test_runs_interactive_flow_when_no_token_and_interactive_true` | unit | PASS |
| 3 | `_authenticate` refreshes an expired-but-refreshable token regardless of `interactive` | `tests/test_santander_auth.py::TestInteractiveAuthentication::test_refreshes_expired_token_without_needing_interactive` | unit | PASS |
| 4 | `_authenticate(interactive=False)` raises `AuthenticationRequiredError` when there's no token, or when the token is invalid and not refreshable — and never calls the interactive flow | `tests/test_santander_auth.py::TestNonInteractiveAuthentication` (3 tests) | unit | PASS |
| 5 | `fetch_transactions` defaults to `interactive=True` and forwards `interactive=False` through to `_authenticate` | `tests/test_santander_fetch.py::TestInteractiveFlag` (2 tests) | unit | PASS |
| 6 | `run_sync` defaults to interactive fetch, forwards `interactive=False`, and propagates `AuthenticationRequiredError` instead of swallowing it | `tests/test_process_transactions.py::TestRunSync::test_defaults_to_interactive_fetch_when_unspecified`, `test_forwards_interactive_false_to_fetch`, `test_propagates_authentication_required_error` | unit | PASS |
| 7 | `POST /api/sync` runs `run_sync(use_remote=False, interactive=False)` and returns its counts as 200 | `tests/test_server.py::TestSyncEndpoint::test_runs_sync_and_returns_counts` | integration | PASS |
| 8 | `/api/sync` requires the bearer token like every other `/api/*` route | `tests/test_server.py::TestSyncEndpoint::test_requires_auth` | integration | PASS |
| 9 | A concurrent sync request while one is in flight gets 409; the lock is released after completion (success or exception) so the next request isn't blocked forever | `tests/test_server.py::TestSyncEndpoint::test_returns_409_when_a_sync_is_already_running`, `test_releases_lock_after_a_completed_sync`, `test_releases_lock_even_when_run_sync_raises` | integration | PASS |
| 10 | A Gmail auth failure maps to 503 with guidance to re-authenticate and upload `token.json` | `tests/test_server.py::TestSyncEndpoint::test_returns_503_when_gmail_authentication_is_unavailable` | integration | PASS |

## Coverage and known gaps
- No coverage tool is wired into this project (`pytest-cov` isn't in `requirements.txt`, confirmed by `--cov` failing with "unrecognized arguments"); coverage is reported qualitatively — every new/changed function (`_authenticate`'s three branches, `fetch_transactions`'s `interactive` forwarding, `run_sync`'s `interactive` forwarding and exception propagation, the `/api/sync` route's success/lock/auth-failure paths) has at least one direct test.
- `pytest tests/ -q` → **338 passed**, 0 failed, 0 skipped (run after both GREEN checkpoints below).
- **Not covered by automated tests**: the frontend "Sync now" button (`common.js`/`styles.css`) — this repo has no JS test runner. Verified by code review against the existing `apiFetch`/`fetchJSON` conventions in `common.js`, not by running it in a browser against a live server this session.
- **Deferred / out of scope for this task**: actually deploying to PythonAnywhere, uploading `token.json` there, and the host-prerequisite risks table in the plan (outbound allowlist, request timeout on large backfills) — those are host-side verification steps, not code changes.

## Checkpoint commits (RED/GREEN, on `sync-now-dashboard`)
1. `f13c0bd` test (RED): reproducers for `AuthenticationRequiredError`, `interactive` forwarding through `fetch_transactions`/`run_sync`, `TOKEN_PATH` override, and the `/api/sync` endpoint — 11 failed (all for the intended reasons: `ImportError`/`TypeError`/`AttributeError`/`NameError`/wrong default), 322 passed (pre-existing suite untouched)
2. `4709303` feat (GREEN): backend implementation — `pytest tests/ -q` → 338 passed
3. (this commit, pending) frontend "Sync now" button + styling — no test runner to gate on; `pytest tests/ -q` still 338 passed after the change
