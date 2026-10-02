# Finance Tracker

Personal finance tracker that aggregates transaction data from multiple bank sources into a unified local dashboard.

## Architecture

1. **Data Ingestion** — Fetch bank notification emails from Gmail, parse transaction data. Runs locally only (needs Google OAuth credentials); if `REMOTE_API_URL` is set, parsed transactions are pushed to a hosted API over HTTP instead of written to a local DB.
2. **Storage** — SQLite (`backend/db/finance_tracker.db`), deduplication via unique index
3. **API Server** — Flask app serving JSON endpoints and the frontend; all `/api/*` routes require a shared-secret bearer token
4. **Dashboard** — Dark mode HTML/CSS/JS frontend with Chart.js visualizations

The server and DB can be deployed to a public host (e.g. PythonAnywhere) so `/api/transactions` is reachable from outside localhost, while Gmail ingestion keeps running locally and pushes to it. See **Hosting & Auth** below.

## Tech Stack

- **Backend**: Python, Flask
- **Email integration**: Gmail API (OAuth2) to pull bank notification emails
- **Storage**: SQLite via `sqlite3` (built-in)
- **Frontend**: HTML, CSS, vanilla JS, Chart.js (CDN)
- **Virtual environment**: `.venv/`

## Project Structure

- `backend/server.py` — Flask API server + static file serving
- `backend/db/storage.py` — SQLite schema + idempotent migrations, insert, query, summary, category (CRUD, merge, suggestions), recurring-expense detection, settings, ignored-transfer rules, and sync-status functions
- `backend/constants.py` — Shared constants (tx types, banks, paths, labels, `UPDATABLE_FIELDS`, `SETTINGS_KEYS`, `IGNORED_ACCOUNT_TRANSFERS` seed)
- `backend/process_transactions.py` — Fetch from Gmail and store (run manually)
- `backend/banks/santander.py` — Gmail fetcher + parsers for 4 email formats (purchase field-style, purchase narrative, transfer, outgoing_transfer); internal-transfer filtering lives in storage, not here. `_authenticate(interactive)` raises `AuthenticationRequiredError` instead of opening a browser when `interactive=False` (used by `POST /api/sync`)
- `backend/db/finance_tracker.db` — SQLite database (DO NOT commit)
- `frontend/html/` — Page templates (index, categorize, transactions, settings, login)
- `frontend/css/` — Stylesheets (shared `styles.css` + page-specific: `categorize.css`, `transactions.css`, `settings.css`, `login.css`)
- `frontend/js/` — Page scripts (`app.js`, `categorize.js`, `transactions.js`, `settings.js`, `login.js`, `common.js`)
- `frontend/manifest.json`, `frontend/icons/` — PWA manifest and icons (installable home-screen app)
- `tests/` — pytest suite for parsers, storage, server API, and email body extraction (test data is inline strings, no fixture files)
- `requirements.txt` — Python dependencies (Flask, Google API, pytest)
- `credentials.json` — Google OAuth credentials (DO NOT commit)
- `token.json` — OAuth token (DO NOT commit)

## Hosting & Auth

- All `/api/*` routes require `Authorization: Bearer <API_TOKEN>` ([backend/server.py](backend/server.py)), checked with a constant-time comparison (`hmac.compare_digest`). Page/static routes (`/`, `/categorize`, `/transactions`, static files) stay open. If `API_TOKEN` is unset, `/api/*` is rejected entirely (fail closed, `503`) rather than running open.
- Failed auth attempts are throttled per source IP (`_failed_attempts` in `backend/server.py`): after `AUTH_MAX_FAILED_ATTEMPTS` failures within `AUTH_LOCKOUT_WINDOW_SECONDS`, further attempts from that IP get `429` without checking the token, until old failures age out of the window. In-memory only — resets on process restart; fine for a single-process personal deployment. If deployed behind a reverse proxy, the proxy must forward the real client IP or all clients will share one lockout bucket.
- `backend/server.py`'s `app.run()` uses `debug=FLASK_DEBUG`, which defaults to off — Flask's interactive debugger allows remote code execution if reached, so it must never be enabled on a publicly reachable host.
- Config is environment-variable driven, set via `os.environ.get(...)` in `backend/constants.py`:
  - `API_TOKEN` — shared secret checked on every `/api/*` request. Unset locally by default (no auth in local dev).
  - `DB_PATH` — overrides the default `backend/db/finance_tracker.db` location (e.g. a persistent dir on a host).
  - `REMOTE_API_URL` — when set on the machine running `process_transactions`, fetched transactions are POSTed to `<REMOTE_API_URL>/api/transactions` with the bearer token instead of written to a local DB. `409` (duplicate) and `200` (`{"ignored": true}`, an internal transfer) responses are both treated as expected and skipped, and counted separately in the ingestion log.
  - `FLASK_DEBUG` — enables Flask's reloader/debugger when set to `true`. Off by default; only for local development, never on a public host.
  - `TOKEN_PATH` — overrides where the Gmail OAuth token (`token.json`) is read/written. Needed on a host so `POST /api/sync` can authenticate without the project's default path.
- Google OAuth credentials (`credentials.json`) and the ingestion script never need to be deployed to the host — only `token.json` (for `POST /api/sync`), `backend/server.py`, `backend/db/storage.py`, `backend/constants.py`, and `frontend/` do.
- `POST /api/sync` runs ingestion directly on the host (`run_sync(use_remote=False, interactive=False)`): behind a non-blocking lock (`409` if a sync is already running), and `_authenticate(interactive=False)` never falls back to the interactive OAuth browser flow — a missing/expired/unrefreshable token raises `AuthenticationRequiredError`, mapped to `503` ("re-authenticate locally and upload token.json") instead of hanging.
- Frontend: `frontend/js/common.js` exposes `apiFetch()`, which prompts for the token on first use, persists it in `localStorage`, attaches it to every request, and clears it on a `401`. All page scripts route `/api/*` calls through `apiFetch()` (or `fetchJSON()`, which wraps it) rather than calling `fetch()` directly.

## Multi-Bank Design

The system is designed to support multiple transaction sources. Santander MX is the first integration; additional banks will be added later. Each bank module exposes `fetch_transactions(since_epoch: int | None = None, interactive: bool = True) -> list[dict]` and pages through its API's full result set itself (no fixed result cap). `interactive=False` must disable any OAuth flow that needs a browser — the server passes it when running ingestion itself (see `POST /api/sync`). Storage and dashboard layers are source-agnostic.

Ingestion is stateless — there's no per-bank last-run file to sync across machines. `process_transactions.py` derives each source's fetch cursor from the newest transaction already stored for that source's banks (`get_latest_tx_date` in `storage.py`, surfaced to remote clients via `GET /api/status`'s `latest_tx_dates`), pulled back by `SYNC_OVERLAP_HOURS` (`constants.py`) so nothing near the boundary is missed; duplicates from the overlap are deduped by the DB's unique index. `SOURCE_BANKS` (`constants.py`) maps each source name to the `bank` values its parsers write.

## Commands

- Activate venv: `source .venv/bin/activate`
- Start dashboard: `python -m backend.server` (serves at http://localhost:5000)
- Fetch new transactions: `python -m backend.process_transactions`
- Run tests: `pytest tests/ -v`
- Run tests with output: `pytest tests/ -v -s`
- Query DB directly: `sqlite3 backend/db/finance_tracker.db`

## Dashboard Pages

- `/` — Overview: one global month selector (URL `?month=`) drives everything — KPI row (income/expenses/net/savings rate, deltas, month-end projection, goal progress), cash-flow chart (grouped bars + net line + goal line) next to the cumulative net-balance chart, breakdown doughnuts (click a slice to drill into `/transactions?month=&category=`), per-category budget progress bars, top merchants + recurring-expense lists, and a quarter/YTD summary. Header shows a sync-freshness indicator and a "Sync now" button that triggers `POST /api/sync`.
- `/categorize` — Work through uncategorized transactions one at a time, pre-filled with a suggested category and up to 8 kind-filtered one-click chips (keys 1–8), plus a batch "apply to all N remaining from X" action. Nav link shows an uncategorized-count badge.
- `/transactions` — Side-by-side income/expense tables, independently sortable and searchable, with totals footer, bank/person filters, a removable category chip, CSV export, and click-a-row-to-edit via the shared modal. View state (`month`, `category`, `bank`, `q`, `eq`) lives in the URL.
- `/settings` — Category management (rename/merge/delete, `kind`, `budget`), savings goal, and ignored-transfer rules — all previously only editable via code/DB.

## API Endpoints

- `GET /api/transactions` — all transactions (filters: `bank`, `type`, `start_date`, `end_date`, `person`)
- `GET /api/summary` — totals grouped by type (filters: `start_date`, `end_date`)
- `GET /api/monthly` — monthly totals by type (filters: `start_date`, `end_date`)
- `GET /api/merchants` — top merchants by spend (filters: `start_date`, `end_date`)
- `GET /api/savings` — monthly savings for a year (param: `year`)
- `GET /api/breakdown` — income/expense grouped by category for a `month` (`YYYY-MM`) or a whole `year` (`YYYY`)
- `GET /api/recurring` — recurring merchants for a `month` (3+ consecutive months, amounts within ±20% of median)
- `GET /api/status` — `{last_synced, uncategorized, latest_tx_dates}` sync-freshness + uncategorized count + per-source ingestion cursor (used by `process_transactions.py` in remote mode)
- `POST /api/sync` — runs ingestion on the host and stores results in its own DB; returns `{inserted, ignored, duplicates}`. `409` if a sync is already running; `503` if Gmail re-authentication is needed (see Hosting & Auth)
- `GET /api/uncategorized` — transactions with no category assigned, each with a `suggested_category`
- `PUT /api/transactions/categorize` — batch assign categories `[{id, category}]`
- `POST /api/transactions` — manually create a transaction `{type, amount, date, ...}` (returns `409` on duplicate, `200 {"ignored": true}` if it matches an ignored-transfer rule)
- `PUT /api/transactions/<id>` — update `amount`, `merchant`, `category`, `sender_bank`, `date`, `type`, `bank`, or `notes` (`409` on dedup collision)
- `DELETE /api/transactions/<id>` — delete a transaction by ID
- `GET /api/categories` — list category names; `?detailed=true` for `[{id, name, kind, budget, count}]`
- `POST /api/categories` — create a new category `{name, kind?}`
- `PUT /api/categories/<id>` — update `name`/`kind`/`budget`; renaming onto an existing name merges categories
- `DELETE /api/categories/<id>` — delete a category (its transactions become uncategorized again)
- `GET /api/settings` / `PUT /api/settings` — read/write whitelisted settings (`SETTINGS_KEYS`; currently `savings_goal`)
- `GET /api/ignored-transfers` / `POST /api/ignored-transfers` / `DELETE /api/ignored-transfers/<id>` — manage internal-transfer ignore rules

## Conventions

- Keep it simple — this is a personal tool, not production software
- Credentials and DB must never be committed to git
- Never log or commit `API_TOKEN`; treat it like `credentials.json`/`token.json`
- Any new frontend JS that touches `/api/*` must call it through `apiFetch()`/`fetchJSON()` in `common.js`, not raw `fetch()`
- Any string rendered via `innerHTML` (e.g. from `dataset.*`, which is already HTML-decoded) must be passed through `escapeHTML()` first
- Each bank parser returns dicts with at minimum: `bank`, `type`, `amount`, `currency`, `date`
- Internal transfers (to/from personal accounts) are filtered out in `insert_transactions` (storage layer) against the `ignored_transfers` table, managed via `/settings` or `/api/ignored-transfers`; `IGNORED_ACCOUNT_TRANSFERS` in `constants.py` is only the seed data for that table
- Dashboard is dark mode — no white backgrounds
- Categories are stored and displayed in UPPERCASE; each has an optional `kind` (`income`/`expense`/`NULL`) and `budget`
- The shared "new transaction" modal (`common.js`) also handles editing and deleting an existing transaction — extend it there rather than building a parallel modal
