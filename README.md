# Finance Tracker

Personal finance tracker that aggregates transaction data from multiple bank sources into a unified local dashboard.

## How it works

1. Bank notification emails arrive in Gmail and are auto-labeled
2. `process_transactions` fetches new emails since the last run, parses transaction data, and stores it in SQLite
3. A Flask server exposes a JSON API and serves a dark-mode dashboard with Chart.js visualizations

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

## Adding a new bank

1. Create `backend/banks/<bank_name>.py`
2. Implement `fetch_transactions() -> list[dict]` following the same pattern
3. Wire it into `backend/process_transactions.py`

Each transaction dict must include at minimum: `bank`, `type`, `amount`, `currency`, `date`.
