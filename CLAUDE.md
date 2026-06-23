# Finance Tracker

Personal finance tracker that aggregates transaction data from multiple bank sources into a unified local dashboard.

## Architecture

1. **Data Ingestion** — Fetch bank notification emails from Gmail, parse transaction data
2. **Storage** — SQLite (`backend/db/finance_tracker.db`), deduplication via unique index
3. **API Server** — Flask app serving JSON endpoints and the frontend
4. **Dashboard** — Dark mode HTML/CSS/JS frontend with Chart.js visualizations

## Tech Stack

- **Backend**: Python, Flask
- **Email integration**: Gmail API (OAuth2) to pull bank notification emails
- **Storage**: SQLite via `sqlite3` (built-in)
- **Frontend**: HTML, CSS, vanilla JS, Chart.js (CDN)
- **Virtual environment**: `.venv/`

## Project Structure

- `backend/server.py` — Flask API server + static file serving
- `backend/db/storage.py` — SQLite schema, insert, query, summary, category functions
- `backend/constants.py` — Shared constants (tx types, paths, labels, ignored transfers)
- `backend/process_transactions.py` — Fetch from Gmail and store (run manually)
- `backend/banks/santander.py` — Gmail fetcher + parsers for 4 email formats (purchase field-style, purchase narrative, transfer, outgoing_transfer)
- `backend/banks/santander_last_run.txt` — Epoch timestamp of last Gmail fetch (runtime, DO NOT commit)
- `backend/db/finance_tracker.db` — SQLite database (DO NOT commit)
- `frontend/html/` — Page templates (index, categorize, transactions)
- `frontend/css/` — Stylesheets (shared styles + page-specific)
- `frontend/js/` — Page scripts (app.js, categorize.js, transactions.js, common.js)
- `tests/` — pytest suite for parsers, storage, server API, and email body extraction (includes .eml fixtures)
- `requirements.txt` — Python dependencies (Flask, Google API, pytest)
- `credentials.json` — Google OAuth credentials (DO NOT commit)
- `token.json` — OAuth token (DO NOT commit)

## Multi-Bank Design

The system is designed to support multiple transaction sources. Santander MX is the first integration; additional banks will be added later. Each bank module exposes `fetch_transactions() -> list[dict]`. Storage and dashboard layers are source-agnostic.

## Commands

- Activate venv: `source .venv/bin/activate`
- Start dashboard: `python -m backend.server` (serves at http://localhost:5000)
- Fetch new transactions: `python -m backend.process_transactions`
- Run tests: `pytest tests/ -v`
- Run tests with output: `pytest tests/ -v -s`
- Query DB directly: `sqlite3 backend/db/finance_tracker.db`

## Dashboard Pages

- `/` — Overview: savings line chart, monthly income/expense doughnut breakdown, quarterly savings cards
- `/categorize` — Assign categories to uncategorized transactions one by one
- `/transactions` — Side-by-side income/expense tables with quarter filter

## API Endpoints

- `GET /api/transactions` — all transactions (filters: `bank`, `type`, `start_date`, `end_date`, `person`)
- `GET /api/summary` — totals grouped by type (filters: `start_date`, `end_date`)
- `GET /api/monthly` — monthly totals by type (filters: `start_date`, `end_date`)
- `GET /api/merchants` — top merchants by spend (filters: `start_date`, `end_date`)
- `GET /api/savings` — monthly savings for a year (param: `year`)
- `GET /api/breakdown` — income/expense grouped by category for a month (param: `month`)
- `GET /api/uncategorized` — transactions with no category assigned
- `PUT /api/transactions/categorize` — batch assign categories `[{id, category}]`
- `GET /api/categories` — list all category names
- `POST /api/categories` — create a new category `{name}`

## Conventions

- Keep it simple — this is a personal tool, not production software
- Credentials and DB must never be committed to git
- Each bank parser returns dicts with at minimum: `bank`, `type`, `amount`, `currency`, `date`
- Internal transfers (to/from personal accounts) are filtered out via `IGNORED_ACCOUNT_TRANSFERS` in constants
- Dashboard is dark mode — no white backgrounds
- Categories are stored and displayed in UPPERCASE
