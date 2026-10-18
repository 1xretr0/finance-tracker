# Open-source readiness — Sub-project 1: Portable deployment + public-repo hygiene

> Design spec (all sections approved in chat). On approval: copy to
> `docs/superpowers/specs/2026-10-17-portable-deployment-design.md`, commit it, then
> invoke `superpowers:writing-plans` to produce the step-by-step implementation plan.

## Context

The repo is already public and currently tailored to one personal PythonAnywhere
deployment (GitHub-webhook auto-deploy, hardcoded paths, personal seed data).
Goal: a self-hostable, MIT-licensed finance tracker for Santander MX users that
works **all-local** or on **any single host** (VPS, home server, Docker PaaS,
PythonAnywhere) with the same config.

### Decisions so far (from the user)
- First-class modes: **All-local** and **Single host** (dashboard + API + DB same origin).
  Static-hosted frontend and separate services are out of scope.
- Packaging: **Docker + plain Python**, same env-var config.
- Split-ingest (`REMOTE_API_URL` push): **keep, document as Advanced**.
- Gmail token on a host: **CLI + copy** (no in-dashboard OAuth).
- First user: **env-var seed** (`ADMIN_USERNAME`/`ADMIN_PASSWORD`).
- Scheduled sync: **no** — manual "Sync now"/CLI only (later sub-project).
- Git history: repo already public → **no rewrite**; sanitize going forward.
  (Verified: no credentials/tokens ever committed; the historic `.db` was a 0-byte file.)
- License: **MIT**.

### Later sub-projects (separate specs)
Scheduled sync · Spanish/i18n docs & UI · general UI/feature polish · more banks.

## Section 1 — Runtime & config (APPROVED)

- **Data directory**: new optional `DATA_DIR` → default home for `finance_tracker.db`,
  `token.json`, `credentials.json`. Unset ⇒ today's paths (backward compatible).
  `DB_PATH`/`TOKEN_PATH` overrides still win; add `CREDENTIALS_PATH` override
  (today hardcoded to project root). All in `backend/constants.py`.
- **`.env` loading**: add `python-dotenv`; one `load_dotenv()` at top of `constants.py`.
  Ship `.env.example` documenting every var + how to generate `API_TOKEN`
  (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).
- **First user seed**: in `init_db()` (`backend/db/storage.py`), if `users` is empty and
  `ADMIN_USERNAME`/`ADMIN_PASSWORD` are set, insert one user with
  `werkzeug.security.generate_password_hash`.
- **`API_TOKEN` required everywhere** (code already fails closed with 503); fix the
  docs/CLAUDE.md claim of "no auth in local dev".
- **Serving**: local `python -m backend.server` (debug off); host
  `gunicorn backend.server:app --workers 1 --threads 4` — single worker is required
  by in-memory lockout + sync lock. `PORT` env (default 5000).
- **`TRUST_PROXY`**: opt-in `werkzeug.middleware.proxy_fix.ProxyFix(x_for=1)` so the
  per-IP lockout sees real client IPs behind Render/Fly/Caddy.
- **Split-ingest** unchanged; documented under "Advanced".

## Section 2 — Packaging & onboarding (APPROVED)

- **Docker**: `Dockerfile` (python:3.12-slim, runtime reqs, non-root, gunicorn),
  `docker-compose.yml` (one service, `./data:/data`, `env_file: .env`, port 5000,
  `DATA_DIR=/data`), `.dockerignore` (.venv, *.db, token/credentials, .git).
- **Gmail auth**: no new `authorize` module — `python -m backend.process_transactions`
  already runs the interactive OAuth flow on first use and writes `token.json`.
  - All-local: run it once.
  - Docker: `docker compose run --rm -p 8765:8765 app python -m backend.process_transactions`.
    Requires changing `run_local_server(port=0)` in `backend/banks/santander.py` to a
    fixed port 8765 with `bind_addr` from `OAUTH_BIND_ADDR` (default `localhost`;
    Dockerfile sets `0.0.0.0`).
  - Remote host: run it on any machine with a browser, copy `token.json` into the data dir.
- **Gmail setup guide**: GCP project → enable Gmail API → **Desktop** OAuth client →
  consent screen → `santander_notifications` label + filter. Call out that a consent
  screen left in "Testing" makes refresh tokens **expire after 7 days**; tell users to
  set it to "In production" (unverified is fine for personal use).

## Section 3 — Hygiene, docs & testing (APPROVED)

### De-personalize
- **`/push` webhook: keep, make generic** (`backend/server.py:489-547`):
  - Route returns **404** unless `GITHUB_WEBHOOK_SECRET` is set (today it 500s on
    `None.encode`).
  - `repo_dir` ← `DEPLOY_REPO_DIR` env (replaces hardcoded `/home/<user>/finance-tracker`);
    reload file ← `DEPLOY_RELOAD_FILE` env (replaces `WSGI_PATH` constant). Missing
    `DEPLOY_REPO_DIR` ⇒ 500 with a clear message; missing reload file ⇒ skip touch.
  - `verify_signature`: use `str.partition("=")` so a malformed header returns 403, not 500.
  - Your PythonAnywhere: set `DEPLOY_REPO_DIR=/home/<user>/finance-tracker` and
    `DEPLOY_RELOAD_FILE=/var/www/<user>_pythonanywhere_com_wsgi.py` in the host `.env`
    **before** deploying this change, or auto-deploy stops.
  - Documented under README "Advanced: auto-deploy on push".
- `IGNORED_ACCOUNT_TRANSFERS = []` in `backend/constants.py` (existing DB rows untouched —
  seeding is `INSERT OR IGNORE`, `backend/db/storage.py:190`). Replace real last-4 digits
  in `README.md` and `tests/test_santander_parser.py` with synthetic ones.
- `requirements.txt`: re-encode UTF-16 → UTF-8; add `gunicorn`, `python-dotenv`;
  move `pytest` to new `requirements-dev.txt` (`-r requirements.txt` + pytest).
- `git rm --cached -r .claude` (already in `.gitignore`; files stay on disk).

### Docs
- `LICENSE` — MIT, © Sebastian Moran.
- `README.md` rewrite: what it is → Quickstart local (venv) → Quickstart Docker →
  Deploy to a host (generic + PythonAnywhere notes; WSGI imports `backend.server:app`) →
  Gmail setup guide → Configuration (→ `.env.example`) → Advanced: split ingest,
  auto-deploy on push → Security notes (API_TOKEN, HTTPS on public hosts, never
  FLASK_DEBUG, TRUST_PROXY, single worker) → Development.
- `CONTRIBUTING.md` — run tests; adding a bank (the `fetch_transactions(since_epoch,
  interactive)` interface + parser dict contract from CLAUDE.md).
- `CLAUDE.md` — update Hosting & Auth / config list / commands for the above.

### Testing
- New pytest cases:
  - `DATA_DIR` / `CREDENTIALS_PATH` resolution and precedence (mirror the `TOKEN_PATH`
    reload tests at `tests/test_server.py:146-153`).
  - Admin seed: empty users + env set ⇒ one hashed user; existing user ⇒ untouched;
    env unset ⇒ none (`tests/test_storage.py`, which already inserts users at :395).
  - `TRUST_PROXY` on ⇒ lockout keyed on `X-Forwarded-For`; off ⇒ `remote_addr`.
  - `/push`: 404 when secret unset; 403 on bad/malformed signature; 200 on valid ping.
  - OAuth flow called with `port=8765` and configured `bind_addr`
    (`tests/test_santander_auth.py` already mocks `run_local_server`).
- CI `.github/workflows/ci.yml`: pytest on Python 3.11 + 3.12; `docker build .`.

## Files touched (summary)
Modify: `backend/constants.py`, `backend/server.py`, `backend/db/storage.py`,
`backend/banks/santander.py`, `requirements.txt`, `README.md`, `CLAUDE.md`,
`tests/test_server.py`, `tests/test_storage.py`, `tests/test_santander_auth.py`,
`tests/test_santander_parser.py`.
Add: `.env.example`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`,
`requirements-dev.txt`, `LICENSE`, `CONTRIBUTING.md`, `.github/workflows/ci.yml`.
Untrack: `.claude/`.

## Verification
1. `pytest tests/ -v` green (existing + new cases).
2. **All-local from a fresh clone**: venv → `pip install -r requirements-dev.txt` →
   `cp .env.example .env` (set API_TOKEN, ADMIN_*) → put `credentials.json` in place →
   `python -m backend.process_transactions` (browser OAuth, emails ingested) →
   `python -m backend.server` → log in with the seeded user, dashboard shows data.
3. **Docker**: fresh `./data` with `credentials.json` → `docker compose run --rm -p 8765:8765
   app python -m backend.process_transactions` completes OAuth from host browser →
   `docker compose up` → login works, "Sync now" returns `{inserted, ignored, duplicates}`,
   data persists across `docker compose down/up`.
4. `/push` with no secret ⇒ 404; with secret + `DEPLOY_*` set, a signed ping ⇒ 200.
5. CI workflow passes on a branch push.

## Out of scope (this sub-project)
Scheduled sync, static-hosted frontend/CORS, in-dashboard OAuth, password change UI,
Spanish/i18n, UI polish, additional banks, git-history rewrite.
