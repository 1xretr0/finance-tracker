# Finance Tracker

Personal finance tracker that aggregates transaction data from multiple bank sources into a unified local dashboard.

## How it works

1. Bank notification emails arrive in Gmail and are auto-labeled
2. `process_transactions` fetches new emails since the last run, parses transaction data, and either stores it in local SQLite or pushes it to a hosted API (see [Hosting & auth](#hosting--auth))
3. A Flask server exposes a JSON API and serves a dark-mode dashboard with Chart.js visualizations. All `/api/*` routes require a bearer token

## Supported banks

### Santander Mexico (`backend/banks/santander.py`)

Parses four notification email formats:

| Type | Description | Key fields |
|------|-------------|------------|
| `purchase` (field-style) | Card purchase — field labels | card_last4, amount, merchant, date |
| `purchase` (narrative) | Card purchase — prose paragraph | card_last4, amount, merchant, date |
| `transfer` | Incoming deposit | account_last4, amount, sender_bank, source_account, tracking_key, concept |
| `outgoing_transfer` | Interbank transfer sent via SuperMovil | account_last4, dest_account_last4, dest_bank, amount, reference |

**Gmail label:** `santander_notifications`

## Setup

### Prerequisites

- Python 3.11+
- A Google Cloud project with the Gmail API enabled
- OAuth 2.0 credentials (`credentials.json`) for the Gmail API

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Gmail configuration

1. Create a Gmail label called `santander_notifications`
2. Set up a filter to auto-label emails from `santander@envio.santander.com.mx` and `notificaciones@notificaciones.santander.com.mx`
3. Place your Google OAuth `credentials.json` in the project root

### First run

```bash
python -m backend.process_transactions
```

On first run, a browser window will open for OAuth consent. The token is saved to `token.json` for subsequent runs.

## Hosting & auth

The server and its SQLite DB can be deployed to a public host (e.g. PythonAnywhere) so `/api/transactions` is reachable from outside `localhost` — for example, so a phone can create transactions directly. Gmail ingestion keeps running locally (it needs the Google OAuth files, which never leave your machine) and pushes parsed transactions to the hosted API instead of writing to a local DB.

All configuration is via environment variables (`backend/constants.py`):

| Variable | Where set | Purpose |
|---|---|---|
| `API_TOKEN` | Host + local machine | Shared secret required as `Authorization: Bearer <token>` on every `/api/*` request, compared with a constant-time check. If unset on the server, all `/api/*` requests are rejected with `503` (fails closed, never runs open). |
| `DB_PATH` | Host | Overrides the default `backend/db/finance_tracker.db` location, e.g. a persistent dir outside the deployed code. |
| `REMOTE_API_URL` | Local machine | When set, `process_transactions` POSTs fetched transactions to `<REMOTE_API_URL>/api/transactions` with the bearer token instead of writing to a local DB. Duplicates (`409`) are skipped, same as local dedup. |
| `FLASK_DEBUG` | Host + local machine | Set to `true` to enable Flask's reloader and interactive debugger. Defaults to off — must stay off on any publicly reachable host, since the debugger allows remote code execution if triggered. |

To deploy only `backend/server.py`, `backend/db/storage.py`, `backend/constants.py`, and `frontend/` — the ingestion script and Google credentials stay local and are never uploaded.

The dashboard prompts for the API token on first load and stores it in `localStorage`; it's cleared automatically if a request comes back `401`.

Repeated failed-auth attempts are throttled per source IP: after 10 failures within a 5-minute window, that IP gets `429` on every `/api/*` request (token or not) until the window rolls off. This state is in-memory and resets on restart. If you put the server behind a reverse proxy, make sure it forwards the real client IP — otherwise every client behind the proxy shares one lockout bucket.

## Usage

### Start the dashboard

```bash
source .venv/bin/activate
python -m backend.server
```

Opens at http://localhost:5000

### Fetch new transactions

```bash
python -m backend.process_transactions
```

### Run tests

```bash
pytest tests/ -v
```

## Project structure

```
finance-tracker/
├── backend/
│   ├── server.py                 # Flask API server + static file serving
│   ├── constants.py              # Shared constants (tx types, paths, labels)
│   ├── process_transactions.py   # Fetch from Gmail and store
│   ├── banks/
│   │   ├── santander.py          # Gmail fetcher + email parsers
│   │   └── santander_last_run.txt # Epoch timestamp of last fetch
│   └── db/
│       ├── storage.py            # SQLite schema, insert, query, category functions
│       └── finance_tracker.db    # SQLite database (DO NOT commit)
├── frontend/
│   ├── html/                     # Page templates (index, categorize, transactions)
│   ├── css/                      # Stylesheets (shared + page-specific)
│   └── js/                       # Page scripts (app, categorize, transactions, common)
├── tests/                        # pytest suite + .eml fixtures
├── requirements.txt              # Python dependencies
├── credentials.json              # Google OAuth credentials (DO NOT commit)
└── token.json                    # OAuth token (DO NOT commit)
```

## Dashboard pages

- `/` — Overview: savings line chart, monthly income/expense doughnut breakdown, quarterly savings cards
- `/categorize` — Assign categories to uncategorized transactions one by one
- `/transactions` — Side-by-side income/expense tables with quarter filter

## API

The Flask server exposes a JSON API used by the dashboard frontend. All endpoints are under `/api/` and require `Authorization: Bearer <API_TOKEN>` (see [Hosting & auth](#hosting--auth)). Page and static routes (`/`, `/categorize`, `/transactions`, CSS/JS) are not gated.

**Transactions** — `GET /api/transactions` returns all transactions with optional filters (`bank`, `type`, `start_date`, `end_date`, `person`). You can also create (`POST`), update (`PUT /<id>`), and delete (`DELETE /<id>`) transactions manually — useful for entries that didn't come from a bank email.

**Summaries and charts** — several read-only endpoints power the dashboard visualizations:
- `/api/summary` — totals grouped by transaction type
- `/api/monthly` — monthly totals broken down by type
- `/api/savings` — per-month savings (income minus purchases and outgoing transfers) for a given year
- `/api/merchants` — top merchants ranked by total spend
- `/api/breakdown` — income and expenses grouped by category for a given month

**Categories** — `GET /api/categories` lists all categories. `POST /api/categories` creates one. `GET /api/uncategorized` returns transactions with no category assigned. `PUT /api/transactions/categorize` batch-assigns categories by transaction ID.

All amounts are in MXN. Dates use ISO 8601 format (`YYYY-MM-DDTHH:MM:SS`).

## Categorization workflow

Transactions are stored without a category by default. The `/categorize` page provides a one-by-one queue to work through them: it fetches the next uncategorized transaction, lets you pick or create a category, and advances to the next. Categories are stored in uppercase (e.g. `FOOD`, `TRANSPORT`).

Once categorized, transactions appear grouped by category in the `/` overview's monthly breakdown chart. You can also re-categorize any transaction from the `/transactions` page.

Categories are free-form — create whatever labels make sense for your spending. They persist in their own `categories` table and are reusable across transactions.

## Tracking by person

Each transaction has an optional `person` field. This is useful for shared-household tracking — tag transactions as belonging to one person or another, then filter by `person` on `GET /api/transactions` to see spending split by individual.

The field is not set by the bank parsers automatically; assign it manually via `PUT /api/transactions/<id>` after import if needed.

## Internal transfer filtering

Transfers to and from personal accounts at other institutions (e.g. a Mercado Pago wallet or an STP account) are automatically ignored during import and never saved to the database. This prevents internal money movements from inflating income or expense totals.

The ignore list lives in `backend/constants.py` under `IGNORED_ACCOUNT_TRANSFERS`:

```python
IGNORED_ACCOUNT_TRANSFERS = [
    {"account_last4": "6184", "bank": "Mercado Pago W"},
    {"account_last4": "8275", "bank": "STP"},
]
```

Add or remove entries here to control which accounts are treated as internal. Matching is done on both `account_last4` and `bank` together, so two different accounts at the same institution won't conflict.

## Adding a new bank

1. Create `backend/banks/<bank_name>.py`
2. Implement `fetch_transactions() -> list[dict]` following the same pattern
3. Wire it into `backend/process_transactions.py`

Each transaction dict must include at minimum: `bank`, `type`, `amount`, `currency`, `date`.
