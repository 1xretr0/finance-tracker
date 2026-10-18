# Finance Tracker

A self-hosted personal finance tracker. It reads your Santander Mexico notification emails from Gmail, parses each purchase and transfer, stores them in a local SQLite database, and shows them in a dark-mode dashboard (Flask API + vanilla JS + Chart.js) that you can also install as a PWA. Your data stays on your own machine or server; the only outside service involved is the Gmail API, read-only.

## Quickstart (local)

Requires Python 3.11+ and Gmail API credentials (see [Gmail setup](#gmail-setup); do that first and save the downloaded file as `credentials.json` in the project root).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Edit `.env` and fill in:

- `API_TOKEN`: a shared secret that every `/api/*` request must carry. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Without it the API answers `503` to everything, even on localhost.
- `ADMIN_USERNAME` and `ADMIN_PASSWORD`: the dashboard login. They only seed the first user, when the database is initialised and the `users` table is empty; the password is stored hashed. Changing them later has no effect (see [resetting the login](#resetting-the-dashboard-login)). Leave either blank and no user is created, so you cannot sign in.

Then fetch your transactions once and start the dashboard:

```bash
python -m backend.process_transactions   # first run opens a browser for Gmail consent
python -m backend.server                 # http://localhost:5000
```

Open http://localhost:5000, sign in with the `ADMIN_USERNAME`/`ADMIN_PASSWORD` you set, and use the "Sync now" button (or re-run `python -m backend.process_transactions`) whenever you want new transactions.

The database is `backend/db/finance_tracker.db` unless you set `DATA_DIR` or `DB_PATH`.

## Quickstart (Docker)

```bash
cp .env.example .env          # compose reads it via env_file; it fails if missing
# edit .env: set API_TOKEN, ADMIN_USERNAME, ADMIN_PASSWORD (see above)

mkdir -p data
cp /path/to/credentials.json data/credentials.json
sudo chown -R 1000:1000 data  # Linux only, see note below; do this after the cp

docker compose up -d          # builds the image on first run; dashboard at http://localhost:5000
```

Then authorise Gmail once. This runs the ingestion command inside the image with the OAuth callback port published:

```bash
docker compose run --rm -p 8765:8765 app python -m backend.process_transactions
```

The container has no browser, so the command prints "Please visit this URL to authorize this application: …" and waits. Open that URL in a browser on your own machine; after you approve, Google redirects to `http://localhost:8765/…`, which the published port delivers to the container. The resulting `token.json` is saved in `./data` and the first sync runs immediately. After that, the dashboard's "Sync now" button works too.

Notes:

- The container runs as uid 1000. On Linux, Docker creates a missing `./data` as root, so create it first and `chown` it as shown (after copying your own files in, since you may not be able to write there afterwards without `sudo`), or the app cannot write the database. Docker Desktop on macOS/Windows is usually not affected.
- The compose file maps `5000:5000` and the image listens on 5000. Do not set `PORT` in `.env` when using it.
- Compose does not publish 8765 by default; the `-p 8765:8765` above is only needed for the one-off authorisation.
- If Docker runs on a remote machine, `localhost:8765` in your own browser will not reach it. Either tunnel the port (`ssh -L 8765:localhost:8765 user@host`) or authorise on a machine with a browser and copy `token.json` into the data directory.
- Everything persistent is in `./data` (SQLite database, `token.json`, `credentials.json`). Back it up by copying that directory. `docker compose down && docker compose up -d` keeps your data.

## Gmail setup

1. Create a project in the [Google Cloud console](https://console.cloud.google.com/).
2. Enable the **Gmail API** for that project.
3. Create an OAuth client ID of type **Desktop app** and download the JSON as `credentials.json` (project root for a local run, the data directory for Docker or a host).
4. Configure the OAuth consent screen (add yourself as a user) and set its publishing status to **"In production"**. A consent screen left in "Testing" makes refresh tokens expire after 7 days, so ingestion would break weekly. You do not need to go through Google verification for personal use; you will just see an "unverified app" warning once during consent.
5. In Gmail, create a label named `santander_notifications`.
6. Create a filter that applies that label to mail from the two Santander sender addresses: `santander@envio.santander.com.mx` and `notificaciones@notificaciones.santander.com.mx`.

The app only requests the read-only Gmail scope (`gmail.readonly`) and only reads messages carrying that label. It fetches everything on the first run, then only messages newer than the newest stored transaction (minus a 48 hour overlap; duplicates are discarded by a unique index).

### Supported email formats

Four Santander notification formats are parsed (`backend/banks/santander.py`):

| Type | Description | Key fields |
|------|-------------|------------|
| `purchase` (field-style) | Card purchase — field labels | card_last4, amount, merchant, date |
| `purchase` (narrative) | Card purchase — prose paragraph | card_last4, amount, merchant, date |
| `transfer` | Incoming deposit | account_last4, amount, sender_bank, source_account, tracking_key, concept |
| `outgoing_transfer` | Interbank transfer sent via SuperMovil | account_last4, dest_account_last4, dest_bank, amount, reference |

Other banks can be added; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Deploying to a host

You can run the server on a VPS or a Python web host so the dashboard is reachable from your phone. The simplest setup keeps everything on the host: the server, the database, and Gmail ingestion triggered from the dashboard's "Sync now" button.

1. Get the code onto the host and `pip install -r requirements.txt`.
2. Put your configuration in `.env` in the project root (or set real environment variables, which win over `.env`). At minimum `API_TOKEN`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`; usually also `DATA_DIR` pointing at a persistent directory.
3. Authorise Gmail on a machine with a browser (`python -m backend.process_transactions` locally) and copy the resulting `token.json` into the host's data directory (or wherever `TOKEN_PATH` points). `credentials.json` and the ingestion CLI do not need to be on the host: "Sync now" only needs `token.json`. If the token is missing or can no longer be refreshed, the sync returns `503` and you repeat this step.
4. Run the app with gunicorn using **exactly one worker**; the failed-login lockout and the sync lock live in process memory:

   ```bash
   gunicorn backend.server:app --bind 127.0.0.1:5000 --workers 1 --threads 4 --timeout 300
   ```

   Use `0.0.0.0` instead of `127.0.0.1` only if your reverse proxy runs on another machine; otherwise plain-HTTP bearer-token traffic would be exposed on port 5000 next to your HTTPS proxy.

   The long timeout is because `POST /api/sync` runs the whole Gmail ingestion inside one request. Put a reverse proxy with HTTPS in front (see [Security notes](#security-notes)).

### PythonAnywhere

Create a web app on a manual-configuration Python version, install `requirements.txt` into its virtualenv, and edit the WSGI file so it imports the Flask app:

```python
import sys
sys.path.insert(0, "/path/to/your/finance-tracker")   # the project checkout

from backend.server import app as application
```

Set the environment variables in the project's `.env`, or with `os.environ[...]` lines in the WSGI file before the app import (PythonAnywhere's web tab has no environment-variable setting), including `DATA_DIR` pointing at a directory that persists. To have the optional [auto-deploy webhook](#auto-deploy-on-push) reload the app, set `DEPLOY_REPO_DIR` to the checkout and `DEPLOY_RELOAD_FILE` to the path of that WSGI file (the app touches it, which makes PythonAnywhere reload). The database schema is created on the first request, so no extra step is needed. PythonAnywhere terminates HTTPS for you. Set `TRUST_PROXY=true` there only if its proxy forwards `X-Forwarded-For` (check that the client IP your app sees is not the same for everyone); otherwise leave it off.

## Configuration

Configuration is read from environment variables, optionally loaded from a `.env` file in the project root (via python-dotenv). Real environment variables always win over `.env` values. Set `ENV_FILE` to load a `.env` from somewhere else. [`.env.example`](.env.example) lists everything; copy it to `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `API_TOKEN` | none (required) | Shared secret sent as `Authorization: Bearer <token>` on every `/api/*` request. If unset the API returns `503`. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | none | Seed one dashboard user, only when the `users` table is empty. Blank means no user. Changing them later has no effect: `/api/login` checks the stored `users` row (hashed password) and returns `API_TOKEN` to the browser. See [resetting the login](#resetting-the-dashboard-login). |
| `DATA_DIR` | unset | Directory holding `finance_tracker.db`, `token.json` and `credentials.json`. Unset keeps the in-repo defaults (`backend/db/` for the database, project root for the others). A relative path is resolved against the project root and `~` is expanded. The Docker image sets `/data`. |
| `DB_PATH`, `TOKEN_PATH`, `CREDENTIALS_PATH` | inside `DATA_DIR` | Override the location of an individual file. These take precedence over `DATA_DIR`. |
| `PORT` | `5000` | Port for `python -m backend.server` and for the Docker image's gunicorn. |
| `TRUST_PROXY` | `false` | Trust one hop of `X-Forwarded-For` so the lockout sees real client IPs. Only behind a reverse proxy. |
| `FLASK_DEBUG` | `false` | Flask reloader and interactive debugger. Local development only. |
| `OAUTH_BIND_ADDR` | `localhost` | Address the Gmail OAuth callback listens on (port is fixed at 8765). The Docker image sets `0.0.0.0`. |
| `REMOTE_API_URL` | unset | See [split ingest](#split-ingest-remote-push). |
| `GITHUB_WEBHOOK_SECRET`, `DEPLOY_REPO_DIR`, `DEPLOY_RELOAD_FILE` | unset | See [auto-deploy on push](#auto-deploy-on-push). |
| `ENV_FILE` | `<project>/.env` | Path of the `.env` file to load. Must be a real environment variable (it cannot be set inside `.env`). |

### Resetting the dashboard login

`/api/login` checks the `users` table in the database, not `.env`. Editing `ADMIN_USERNAME`/`ADMIN_PASSWORD` after the first user exists does nothing, and there is no in-app way to change a password. To change it, delete the user, update the two values in `.env`, and restart so the next database initialisation seeds the new user. Both paths below use the `sqlite3` command-line tool on the host (the Docker image does not include it).

Local run (database is `backend/db/finance_tracker.db`, or `$DATA_DIR/finance_tracker.db` if you set `DATA_DIR`):

```bash
sqlite3 backend/db/finance_tracker.db "DELETE FROM users"
# edit ADMIN_USERNAME / ADMIN_PASSWORD in .env, then (re)start the server
python -m backend.server
```

Docker (database is `data/finance_tracker.db`; `sudo` is needed if `data/` is owned by uid 1000 and you are a different user):

```bash
sudo sqlite3 data/finance_tracker.db "DELETE FROM users"
# edit ADMIN_USERNAME / ADMIN_PASSWORD in .env, then recreate the container
docker compose up -d --force-recreate
```

Use `up -d --force-recreate` rather than `docker compose restart`: compose reads `.env` when the container is created, so a plain restart keeps the old values.

## Advanced

### Split ingest (remote push)

Instead of running everything on one machine, you can host only the server and database, and keep Gmail ingestion on a machine that has your OAuth files. On the ingestion machine set `REMOTE_API_URL=https://example.com` and the same `API_TOKEN` as the server. `python -m backend.process_transactions` then POSTs each parsed transaction to `<REMOTE_API_URL>/api/transactions` with the bearer token instead of writing a local DB, and asks `GET /api/status` for the newest stored transaction to derive its fetch cursor. Duplicates (`409`) and internal transfers (`200 {"ignored": true}`) are skipped and counted separately in the log.

### Auto-deploy on push

If you deploy from a git checkout, the server can update itself when you push to GitHub. Set `GITHUB_WEBHOOK_SECRET` on the server and add a GitHub webhook for push events to `https://example.com/push` (content type `application/json`, same secret). A valid signed push event makes the server run `git pull origin main` in `DEPLOY_REPO_DIR` (the branch name is fixed, and `git` must be available on the host), then touch `DEPLOY_RELOAD_FILE` (for example a PythonAnywhere WSGI file) so the host reloads the app. The webhook only pulls and reloads; it does NOT install dependencies, so after a change to `requirements.txt` run `pip install -r requirements.txt` on the host yourself. Without `GITHUB_WEBHOOK_SECRET`, `/push` returns `404`. If `DEPLOY_REPO_DIR` is missing, a push event returns `500`; `DEPLOY_RELOAD_FILE` is optional.

## Security notes

- `API_TOKEN` is required. Without it every `/api/*` call fails with `503`; the server never runs open. The page routes (`/`, `/login`, static files) are not gated, but they contain no data.
- Serve the app over HTTPS on any public host. The token is a bearer secret sent on every request and returned by `/api/login`.
- Never set `FLASK_DEBUG=true` on a reachable host: Flask's interactive debugger allows remote code execution.
- Set `TRUST_PROXY=true` only when a reverse proxy in front sets `X-Forwarded-For`. Without a proxy, a client could spoof that header and dodge the lockout. Behind a proxy but without `TRUST_PROXY`, every client appears to have the proxy's IP and they all share one lockout bucket.
- Run a single worker. After 10 failed attempts within 5 minutes, a source IP gets `429` on `/api/*` until the failures age out. That state, and the lock preventing concurrent syncs, is in memory per process, so multiple workers would not share them.
- Never commit or log `.env`, `API_TOKEN`, `credentials.json`, `token.json` or the database. The Docker build context excludes them.

## Development

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding a bank and project conventions.

## Dashboard pages

- `/` — Overview: a single global month selector drives everything on the page — a KPI row (income, expenses, net, savings rate, deltas vs. last month/3-month average, month-end spend projection, progress vs. a savings goal), a cash-flow chart (grouped income/expense bars + a net line + an optional goal line) next to the cumulative net-balance chart, income/expense breakdown doughnuts (click a slice to drill into `/transactions` filtered to that month + category), per-category budget progress bars, top merchants and recurring-expense lists, and a quarter/YTD summary. The header shows a data-freshness indicator ("Synced 2h ago") and a "Sync now" button.
- `/categorize` — Work through uncategorized transactions one at a time. Each one is pre-filled with a suggested category (based on how the same merchant/sender was categorized before), plus up to 8 one-click category chips (numbered 1–8 for keyboard shortcuts) filtered to that transaction's income/expense kind. An "apply to all N remaining from X" checkbox batch-categorizes every other queued transaction with the same description in one action. The nav link shows a badge with the current uncategorized count.
- `/transactions` — Side-by-side income/expense tables, each independently sortable and searchable, with a totals footer, bank/person filters, a removable category filter chip, and CSV export. Click any row to edit or delete it in the shared modal; the month, filters and search terms are kept in the URL.
- `/settings` — Manage categories (rename, tag as income/expense, set a monthly budget, merge into another category, or delete), set a monthly savings goal, and manage the ignored-transfer rules without touching code.
- `/login` — Sign in as the user seeded from `ADMIN_USERNAME`/`ADMIN_PASSWORD` on first initialisation.

The app is installable as a PWA (manifest + icons); on screens under 600px a floating "+" button opens the quick-add modal.

## API

The Flask server exposes a JSON API used by the dashboard. All endpoints are under `/api/` and require `Authorization: Bearer <API_TOKEN>`, except `POST /api/login`, which takes `{username, password}` and returns the token (it still counts toward the failed-attempt lockout).

**Transactions** — `GET /api/transactions` returns all transactions with optional filters (`bank`, `type`, `start_date`, `end_date`, `person`). You can also create (`POST`), update (`PUT /<id>`), and delete (`DELETE /<id>`) transactions manually. `PUT /<id>` accepts `amount`, `merchant`, `category`, `sender_bank`, `date`, `type`, `bank` and `notes`, and returns `409` on a dedup collision. `POST` returns `409` on a duplicate and `200 {"ignored": true}` instead of inserting when the transaction matches an ignored-transfer rule.

**Summaries and charts** — read-only endpoints power the dashboard:
- `/api/summary` — totals grouped by transaction type
- `/api/monthly` — monthly totals broken down by type
- `/api/savings` — per-month savings (income minus purchases and outgoing transfers) for a given `year`
- `/api/merchants` — top merchants ranked by total spend
- `/api/breakdown` — income and expenses grouped by category, for a given `month` (`YYYY-MM`) or a whole `year` (`YYYY`)
- `/api/recurring?month=` — merchants that appear in 3+ consecutive months (of the 6 leading up to `month`) with amounts within ±20% of their median
- `/api/status` — `{last_synced, uncategorized, latest_tx_dates}`: when ingestion last wrote to the DB, how many transactions still need a category, and the newest stored transaction per ingestion source

**Sync** — `POST /api/sync` runs Gmail ingestion on the server and returns `{inserted, ignored, duplicates}`. `409` if a sync is already running; `503` if the Gmail token is missing or expired and cannot be refreshed (re-authenticate locally and copy `token.json` to the server).

**Categories** — `GET /api/categories` lists category names; `?detailed=true` returns `[{id, name, kind, budget, count}]`. `POST /api/categories` creates one (`{name, kind?}`). `PUT /api/categories/<id>` updates `name`/`kind`/`budget`; renaming onto an existing name merges the two categories. `DELETE /api/categories/<id>` removes a category and its transactions become uncategorized. `GET /api/uncategorized` returns transactions with no category, each with a `suggested_category`. `PUT /api/transactions/categorize` batch-assigns categories by transaction ID.

**Settings & ignored transfers** — `GET/PUT /api/settings` reads/writes whitelisted keys (currently `savings_goal`; `PUT` accepts a non-negative number or `null`). `GET /api/ignored-transfers` lists the rules used to skip internal transfers on import; `POST` (`{account_last4, bank}`) adds one and `DELETE /<id>` removes one.

All amounts are in MXN. Dates use ISO 8601 format (`YYYY-MM-DDTHH:MM:SS`).

## Categorization workflow

Transactions are stored without a category by default. The `/categorize` page is a one-by-one queue: it fetches the next uncategorized transaction (pre-filled with a suggested category and quick-pick chips), lets you pick, type or create a category, and advances to the next, optionally applying the same category to every other queued transaction with a matching description. Categories are stored in uppercase (e.g. `FOOD`, `TRANSPORT`).

Once categorized, transactions appear grouped by category in the overview's breakdown chart and budget bars. You can re-categorize any transaction from `/transactions`, or manage categories in bulk on `/settings`. Categories are free-form and live in their own `categories` table (`name`, `kind`, `budget`). `kind` (`income`/`expense`/`NULL`) is set based on the transaction type a category is first used with.

## Tracking by person

Each transaction has an optional `person` field, useful for shared-household tracking: filter by `person` on `GET /api/transactions` to see spending split by individual. The bank parsers do not set it; assign it via `PUT /api/transactions/<id>` after import.

## Internal transfer filtering

Transfers to and from your own accounts at other institutions (for example a wallet or a second bank account) can be ignored during import so they do not inflate income or expense totals. The list ships empty. Add rules (`account_last4` plus `bank`, matched together and case-insensitively on the bank name) on `/settings`, or via `GET/POST /api/ignored-transfers` and `DELETE /api/ignored-transfers/<id>`.

Filtering happens in `insert_transactions` (storage layer), not in the bank parsers, so it applies the same way for a local DB and for the hosted API (a matching `POST /api/transactions` returns `200 {"ignored": true}`). `IGNORED_ACCOUNT_TRANSFERS` in `backend/constants.py` is only an optional seed list used to populate the table the first time it is empty, for example `{"account_last4": "1234", "bank": "Example Bank"}`.

## License

[MIT](LICENSE)
