# Portable Deployment & Public-Repo Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the finance tracker runnable all-local or on any single host (venv or Docker) from one env-var config, and strip personal/host-specific details so the public repo is usable by other Santander MX users.

**Architecture:** Keep the monolith (Flask serves dashboard + API + SQLite). Add one `DATA_DIR`, `.env` loading, an env-seeded first user, an opt-in proxy-trust setting, a generic `/push` hook, a fixed OAuth port for Docker, then Docker/CI/docs on top.

**Tech Stack:** Python 3.11+, Flask 3.1, SQLite, pytest, python-dotenv, gunicorn, Docker.

**Spec:** `docs/superpowers/specs/2026-10-17-portable-deployment-design.md`

## Global Constraints

- Python 3.11+; CI matrix 3.11 and 3.12; Docker base `python:3.12-slim`.
- Backward compatible: with none of the new env vars set, DB/token/credentials paths and behavior are unchanged.
- Path precedence: explicit `DB_PATH` / `TOKEN_PATH` / `CREDENTIALS_PATH` > `DATA_DIR` > project defaults.
- Server runs gunicorn with `--workers 1 --threads 4` (lockout and sync lock are in-process).
- `API_TOKEN` stays required for `/api/*` (503 if unset); it and `.env` are never logged or committed.
- Only new dependencies: `python-dotenv`, `gunicorn`. `pytest` moves to `requirements-dev.txt`.
- Match file style: tabs in `backend/banks/santander.py`, 4 spaces elsewhere.
- No real account digits, usernames or hostnames anywhere in the repo.
- Tests: pytest, inline data, no fixture files; run `pytest tests/ -v` from the repo root with the venv active.

## Review Focus

1. `DATA_DIR` points at a directory that doesn't exist yet → `init_db()` creates it instead of `unable to open database file` (Task 2 test).
2. `ADMIN_USERNAME=` / `ADMIN_PASSWORD=` left blank (copied from `.env.example`) → no user is created, never a user with an empty password (Task 2 test).
3. `POST /api/sync` runs Gmail ingestion inside one request and outlives gunicorn's default 30 s worker timeout → Dockerfile sets `--timeout 300` (Task 6 check).
4. A developer's real `.env` leaks into the test run (or gets committed) → `tests/conftest.py` points `ENV_FILE` at `os.devnull`, `.gitignore` lists `.env` (Task 1 tests/check).
5. `TRUST_PROXY` off must ignore a client-supplied `X-Forwarded-For`, otherwise the lockout can be dodged by spoofing it (Task 3 test).

---

### Task 1: Config surface (`DATA_DIR`, `.env`, new settings, requirements)

**Files:**
- Modify: `backend/constants.py`, `requirements.txt`, `.gitignore`
- Create: `tests/conftest.py`, `tests/test_config.py`, `requirements-dev.txt`

**Interfaces:**
- Produces (module-level in `backend/constants.py`): `DATA_DIR: str | None`; `DB_PATH`, `TOKEN_FILE`, `CREDENTIALS_FILE: str`; `SERVER_PORT: int`; `ADMIN_USERNAME`, `ADMIN_PASSWORD: str | None`; `TRUST_PROXY: bool`; `DEPLOY_REPO_DIR`, `DEPLOY_RELOAD_FILE: str | None`; `OAUTH_PORT: int` (8765); `OAUTH_BIND_ADDR: str` (default `"localhost"`).

- [ ] **Step 1: Write failing tests in `tests/test_config.py`.** Use a fixture that reloads `backend.constants` after each test (same `importlib.reload` pattern as `tests/test_server.py:143-155`). Tests, with exact assertions:
  - `test_without_data_dir_paths_keep_legacy_defaults`: `DATA_DIR` unset → `DB_PATH` ends with `backend/db/finance_tracker.db`; `TOKEN_FILE` ends `token.json`; `CREDENTIALS_FILE` ends `credentials.json`; both of the latter sit in the project root.
  - `test_data_dir_relocates_db_token_and_credentials`: `DATA_DIR=<tmp>` → `DB_PATH == <tmp>/finance_tracker.db`, `TOKEN_FILE == <tmp>/token.json`, `CREDENTIALS_FILE == <tmp>/credentials.json`.
  - `test_explicit_paths_beat_data_dir`: `DB_PATH`, `TOKEN_PATH`, `CREDENTIALS_PATH` set alongside `DATA_DIR` → the explicit values win.
  - `test_port_defaults_to_5000_and_reads_port_env`: unset → `5000`; `PORT=8080` → `8080` (int).
  - `test_trust_proxy_defaults_off_and_parses_true`: unset → `False`; `"true"` → `True`.
  - `test_env_file_values_are_loaded`: `ENV_FILE=<tmp>/.env` containing `ADMIN_USERNAME=fromfile` → `constants.ADMIN_USERNAME == "fromfile"`; make sure the loaded var is removed from `os.environ` at teardown.
  - `test_real_env_beats_env_file`: same file, but `ADMIN_USERNAME=fromenv` set in the environment → `"fromenv"`.
- [ ] **Step 2: Run** `pytest tests/test_config.py -v` → FAIL (attributes missing).
- [ ] **Step 3: Implement in `backend/constants.py`.** At the top, after defining `_PROJECT_ROOT` (move it above its current spot), call `load_dotenv(os.environ.get("ENV_FILE", os.path.join(_PROJECT_ROOT, ".env")))` (no override of real env). Then: `DATA_DIR = os.environ.get("DATA_DIR")`; `DB_PATH`, `TOKEN_FILE` (`TOKEN_PATH`), `CREDENTIALS_FILE` (new `CREDENTIALS_PATH`) resolved per the precedence above; `SERVER_PORT = int(os.environ.get("PORT", 5000))`; the other new constants from Interfaces, bool parsing like `FLASK_DEBUG`. Leave `WSGI_PATH` and `GITHUB_WEBHOOK_SECRET` for Task 3.
- [ ] **Step 4: Create `tests/conftest.py`** setting `os.environ["ENV_FILE"] = os.devnull` at import time with a one-line comment (keeps a developer's real `.env` out of the suite).
- [ ] **Step 5: Requirements.** Re-encode `requirements.txt` from UTF-16 to UTF-8 (`iconv -f UTF-16 -t UTF-8`), drop `pytest`, add `python-dotenv==1.0.1` and `gunicorn==23.0.0`. Create `requirements-dev.txt` containing `-r requirements.txt` and `pytest==9.1.0` (the version currently pinned). Add `.env` and `data/` to `.gitignore`. Run `file requirements.txt` → expect ASCII/UTF-8 text; `pip install -r requirements-dev.txt` succeeds.
- [ ] **Step 6: Run** `pytest tests/ -v` → all pass (Review Focus 4: also run once with a throwaway project-root `.env` containing `TOKEN_PATH=/x`, confirm still green, then delete it).
- [ ] **Step 7: Commit** `feat: DATA_DIR, .env loading and new config constants`.

---

### Task 2: First-user seed and data-dir creation

**Files:**
- Modify: `backend/db/storage.py` (imports at `:10-20`, `init_db` at `:105`), `tests/test_storage.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `DB_PATH` (import the first two into `storage`'s namespace like `DB_PATH`, so tests can `monkeypatch.setattr(storage, ...)`).
- Produces: `init_db()` now also creates the DB's parent dir and seeds one user; private `_seed_admin_user(conn: sqlite3.Connection) -> None`.

- [ ] **Step 1: Write failing tests** in `tests/test_storage.py` (the autouse fixture already ran `init_db()` on one tmp DB, so each test points `storage.DB_PATH` at a fresh tmp file before calling `init_db()` again):
  - `test_init_db_seeds_admin_user_when_users_empty`: with `ADMIN_USERNAME="admin"`, `ADMIN_PASSWORD="pw-123"` → exactly one `users` row, `username == "admin"`, `check_password_hash(row["password_hash"], "pw-123")` is true, hash is not the plaintext.
  - `test_init_db_leaves_existing_users_alone`: insert a user first, run `init_db()` with admin env set → still one row, original username.
  - `test_init_db_without_admin_env_creates_no_user`: both `None` → zero rows.
  - `test_init_db_ignores_blank_admin_credentials`: parametrized `("", "pw")`, `("admin", "")`, `("", "")` → zero rows.
  - `test_init_db_creates_missing_data_dir`: `DB_PATH = <tmp>/nested/dir/test.db` → `init_db()` succeeds and the file exists.
  In `tests/test_server.py` `TestLoginEndpoint`: `test_login_with_env_seeded_admin` — seed via `init_db()` with admin env set, `POST /api/login` with those credentials → 200 and `username` in the JSON.
- [ ] **Step 2: Run** `pytest tests/test_storage.py tests/test_server.py -v -k "admin or data_dir or seeded"` → FAIL.
- [ ] **Step 3: Implement.** In `init_db()` first `os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)`; after the `users` table exists, call `_seed_admin_user(conn)`, which inserts only if both env values are non-empty and `users` is empty, using `werkzeug.security.generate_password_hash` and `INSERT OR IGNORE` (unique username covers the multi-process race), `created_at` as an ISO timestamp like other rows.
- [ ] **Step 4: Run** `pytest tests/ -v` → pass.
- [ ] **Step 5: Commit** `feat: seed first dashboard user from ADMIN_USERNAME/ADMIN_PASSWORD`.

---

### Task 3: Server — proxy trust and generic `/push` hook

**Files:**
- Modify: `backend/server.py` (imports `:46-55`, webhook block `:488-547`, module bottom), `backend/constants.py` (delete `WSGI_PATH`), `tests/test_server.py`

**Interfaces:**
- Consumes: `TRUST_PROXY`, `GITHUB_WEBHOOK_SECRET`, `DEPLOY_REPO_DIR`, `DEPLOY_RELOAD_FILE`.
- Produces: `apply_proxy_fix(flask_app: Flask, enabled: bool) -> None` (wraps `flask_app.wsgi_app` with `werkzeug.middleware.proxy_fix.ProxyFix(x_for=1)` when enabled; called once at module level with `TRUST_PROXY`); `verify_signature(payload: bytes, signature_header: str | None, secret: str) -> bool` (never raises on a malformed header); `trigger_reload() -> None` (touches `DEPLOY_RELOAD_FILE` if set and existing).

- [ ] **Step 1: Write failing tests** in `tests/test_server.py`. A fixture saves and restores `app.wsgi_app`.
  - `TestProxyTrust`:
    - `test_trust_proxy_off_ignores_forwarded_for` (Review Focus 5): `apply_proxy_fix(app, False)`, `AUTH_MAX_FAILED_ATTEMPTS=3`; 3 bad-token requests from the same `REMOTE_ADDR` each with a different `X-Forwarded-For` → 4th request (valid token) is 429.
    - `test_trust_proxy_on_keys_lockout_on_forwarded_for`: `apply_proxy_fix(app, True)`; 3 bad requests with `X-Forwarded-For: 1.1.1.1` → a 4th from that address is 429, while a valid-token request with `X-Forwarded-For: 2.2.2.2` is 200.
  - `TestPushWebhook` (sign bodies with `hmac` + `sha256`, header `X-Hub-Signature-256: sha256=<hex>`):
    - `test_push_is_404_when_secret_unset`.
    - `test_push_rejects_wrong_signature_with_403`.
    - `test_push_rejects_malformed_signature_header_with_403`: headers `"garbage"` and `"sha256"`.
    - `test_push_ping_with_valid_signature_returns_200`.
    - `test_push_event_without_deploy_repo_dir_returns_500`: valid signature, `X-GitHub-Event: push`, `DEPLOY_REPO_DIR=None` → 500, JSON message mentions `DEPLOY_REPO_DIR`.
    - `test_push_event_pulls_in_configured_dir`: patch `server.subprocess.check_output` and `server.threading.Thread`; `DEPLOY_REPO_DIR=<tmp>` → 200, `check_output` called with `cwd=<tmp>`.
    (Monkeypatch `server.GITHUB_WEBHOOK_SECRET` etc., not the env.)
- [ ] **Step 2: Run** `pytest tests/test_server.py -v -k "Proxy or Push"` → FAIL.
- [ ] **Step 3: Implement** the interfaces above. `/push` returns 404 JSON when `GITHUB_WEBHOOK_SECRET` is falsy, checked before the signature; `verify_signature` splits with `str.partition("=")`; `repo_dir` comes from `DEPLOY_REPO_DIR`; remove `WSGI_PATH` from `server.py` imports and `constants.py`.
- [ ] **Step 4: Run** `pytest tests/ -v` → pass. `rg -n "WSGI_PATH|/home/" backend` → no hits.
- [ ] **Step 5: Commit** `feat: TRUST_PROXY setting and env-configured /push webhook`.

---

### Task 4: Fixed OAuth port for containerised auth

**Files:**
- Modify: `backend/banks/santander.py` (imports `:28-29`, `_authenticate` `:136`; tabs), `tests/test_santander_auth.py`

**Interfaces:**
- Consumes: `OAUTH_PORT`, `OAUTH_BIND_ADDR` (import into `santander`'s namespace).

- [ ] **Step 1: Write failing test** `test_interactive_flow_uses_fixed_port_and_bind_addr` in `tests/test_santander_auth.py` (reuse its fake flow): `monkeypatch.setattr(santander, "OAUTH_BIND_ADDR", "0.0.0.0")`, run `_authenticate(interactive=True)` with no token file → `fake_flow.run_local_server.assert_called_once_with(port=8765, bind_addr="0.0.0.0")`. Update any existing assertion on `run_local_server(port=0)`.
- [ ] **Step 2: Run** `pytest tests/test_santander_auth.py -v` → FAIL.
- [ ] **Step 3: Implement:** `flow.run_local_server(port=OAUTH_PORT, bind_addr=OAUTH_BIND_ADDR)`.
- [ ] **Step 4: Run** `pytest tests/ -v` → pass.
- [ ] **Step 5: Commit** `feat: fixed OAuth callback port so Docker can publish it`.

---

### Task 5: De-personalize the repo

**Files:**
- Modify: `backend/constants.py`, `tests/test_storage.py` (`:80`, `:512-514`, `:797-827`), `tests/test_santander_parser.py`, `README.md`
- Untrack: `.claude/`

- [ ] **Step 1: Write failing test** `test_default_ignored_transfer_seed_is_empty`: `assert constants.IGNORED_ACCOUNT_TRANSFERS == []`. Rewrite `test_ignored_transfers_seeded_from_constants` (`tests/test_storage.py:512`) to monkeypatch `storage.IGNORED_ACCOUNT_TRANSFERS` with `[{"account_last4": "5555", "bank": "Example Bank"}]`, init a fresh tmp DB, and assert that rule is present.
- [ ] **Step 2: Run** the two tests → the new one FAILS.
- [ ] **Step 3: Implement.** Set `IGNORED_ACCOUNT_TRANSFERS = []` (keep the comment saying it's seed data for the table). Replace the real last-4 values with synthetic ones across `README.md`, `tests/test_storage.py`, `tests/test_santander_parser.py`: `sd '\b6184\b' '5555'`, `sd '\b8275\b' '7777'`, `sd '\b6031\b' '8888'`; review `git diff` so no unrelated number changed. Then `git rm -r --cached .claude -q` (files stay on disk; already in `.gitignore`).
- [ ] **Step 4: Run** `pytest tests/ -v` → pass. `rg -n "6184|8275|6031" . -g '!.venv' -g '!.git'` → no hits. `git ls-files .claude` → empty.
- [ ] **Step 5: Commit** `chore: remove personal seed data and stop tracking .claude`.

---

### Task 6: Docker packaging and `.env.example`

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`

**Decisions to implement:**
- `Dockerfile`: `python:3.12-slim`; `ENV DATA_DIR=/data OAUTH_BIND_ADDR=0.0.0.0 PORT=5000 PYTHONUNBUFFERED=1`; install `requirements.txt` first (layer cache), then copy `backend/` and `frontend/` only; create uid-1000 user and `/data` owned by it; `USER` that user; `VOLUME /data`; shell-form `CMD` so `$PORT` expands: `gunicorn backend.server:app --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 300`.
- `docker-compose.yml`: one service `app`, `build: .`, `env_file: .env`, `environment: [DATA_DIR=/data]`, `ports: ["5000:5000"]`, `volumes: ["./data:/data"]`, `restart: unless-stopped`.
- `.dockerignore`: `.git`, `.venv`, `.env`, `data`, `*.db*`, `credentials.json`, `token.json`, `tests`, `docs`, `.claude`, `__pycache__`.
- `.env.example`: every variable (`API_TOKEN`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `PORT`, `TRUST_PROXY`, `FLASK_DEBUG`, `DATA_DIR` commented out, `DB_PATH`/`TOKEN_PATH`/`CREDENTIALS_PATH` commented out, `OAUTH_BIND_ADDR` commented, `REMOTE_API_URL`, `GITHUB_WEBHOOK_SECRET`, `DEPLOY_REPO_DIR`, `DEPLOY_RELOAD_FILE`) with a one-line comment each; `API_TOKEN` comment shows `python -c "import secrets; print(secrets.token_urlsafe(32))"`; blank `ADMIN_*` values.

- [ ] **Step 1: Create the four files** per the decisions above.
- [ ] **Step 2: Static checks:** `rg -- "--timeout 300" Dockerfile` matches (Review Focus 3); `rg "token.json|credentials.json|\.env" .dockerignore` matches all three.
- [ ] **Step 3: Build and smoke-test** (requires Docker; if unavailable, say so in the report and leave to CI): `docker build -t finance-tracker .` succeeds; `mkdir -p data && docker run --rm -d --name ft -e API_TOKEN=x -e ADMIN_USERNAME=a -e ADMIN_PASSWORD=b -p 5000:5000 -v "$PWD/data:/data" finance-tracker`; `curl -s -H "Authorization: Bearer x" localhost:5000/api/status` returns JSON with `uncategorized`; `curl -s -X POST localhost:5000/api/login -H 'Content-Type: application/json' -d '{"username":"a","password":"b"}'` returns a token; `data/finance_tracker.db` exists on the host; `docker stop ft`.
- [ ] **Step 4: Commit** `feat: Dockerfile, compose file and .env.example`.

---

### Task 7: Docs — LICENSE, README, CONTRIBUTING, CLAUDE.md

**Files:**
- Create: `LICENSE`, `CONTRIBUTING.md`
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: `LICENSE`:** standard MIT text, `Copyright (c) 2026 Sebastian Moran`.
- [ ] **Step 2: Rewrite `README.md`** with these sections, in order: What it is (one paragraph: self-hosted, Santander MX email → dashboard); Quickstart (local venv: install `requirements.txt`, `cp .env.example .env`, set `API_TOKEN`/`ADMIN_*`, ingest once, `python -m backend.server`); Quickstart (Docker: `mkdir -p data` first so the bind mount is writable by the non-root user; `docker compose up -d`; OAuth via `docker compose run --rm -p 8765:8765 app python -m backend.process_transactions`); Gmail setup (GCP project → enable Gmail API → **Desktop** OAuth client → consent screen **set to "In production"** because "Testing" refresh tokens expire after 7 days → `santander_notifications` label + filters for the two sender addresses already in the current README); Deploying to a host (copy `token.json` into the data dir; gunicorn single-worker; PythonAnywhere notes: WSGI file imports `backend.server:app`, set env vars in `.env`); Configuration (table pointing to `.env.example`); Advanced: split ingest (`REMOTE_API_URL`) and auto-deploy on push (`GITHUB_WEBHOOK_SECRET`, `DEPLOY_REPO_DIR`, `DEPLOY_RELOAD_FILE`); Security notes (`API_TOKEN` required, serve over HTTPS on public hosts, never `FLASK_DEBUG` publicly, `TRUST_PROXY` only behind a proxy that sets `X-Forwarded-For`, one worker); Development (`pip install -r requirements-dev.txt`, `pytest tests/ -v`). Keep the supported-email-formats table.
- [ ] **Step 3: `CONTRIBUTING.md`:** how to run tests; adding a bank = module in `backend/banks/` exposing `fetch_transactions(since_epoch: int | None = None, interactive: bool = True) -> list[dict]`, parser dicts with at least `bank`, `type`, `amount`, `currency`, `date`, register the source in `SOURCE_BANKS`; tests use inline email strings.
- [ ] **Step 4: Update `CLAUDE.md`:** Hosting & Auth bullets for `DATA_DIR`, `CREDENTIALS_PATH`, `PORT`, `TRUST_PROXY`, `ADMIN_*`, `DEPLOY_*`, `ENV_FILE`; correct "Unset locally by default (no auth in local dev)" (the API fails closed without `API_TOKEN`); Project Structure gets the new files; remove `WSGI_PATH`.
- [ ] **Step 5: Verify:** `rg -n "no auth in local dev|Unset locally by default|WSGI_PATH" README.md CLAUDE.md CONTRIBUTING.md` → no hits; every command in the README quickstarts was run at least once in Task 6 or Task 9.
- [ ] **Step 6: Commit** `docs: MIT license, README rewrite, CONTRIBUTING, CLAUDE.md updates`.

---

### Task 8: CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflow:** triggers `push` to `main` and `pull_request`; job `test` with matrix Python `3.11`, `3.12` running `pip install -r requirements-dev.txt` then `pytest tests/ -v`; job `docker` running `docker build -t finance-tracker .`.
- [ ] **Step 2: Validate locally:** `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"` (or any YAML parser) exits 0.
- [ ] **Step 3: Commit** `ci: run tests on 3.11/3.12 and build the Docker image`.
- [ ] **Step 4: After the user pushes a branch:** confirm both jobs go green (cannot be verified locally).

---

### Task 9: End-to-end check (needs the user's Gmail credentials)

- [ ] **Step 1: All-local from a fresh clone** (spec Verification 2): `pip install -r requirements-dev.txt`, `cp .env.example .env`, set `API_TOKEN`/`ADMIN_*`, place `credentials.json`, `python -m backend.process_transactions` (browser OAuth completes on port 8765, emails ingested), `python -m backend.server`, log in as the seeded user, dashboard shows data.
- [ ] **Step 2: Docker** (spec Verification 3): fresh `./data` with `credentials.json`; OAuth via `docker compose run --rm -p 8765:8765 app python -m backend.process_transactions`; `docker compose up -d`; login works; "Sync now" returns `{inserted, ignored, duplicates}`; data persists across `docker compose down && up`.
- [ ] **Step 3: `/push`** (spec Verification 4): unset secret → 404; with secret and `DEPLOY_*` set, a signed ping → 200.
- [ ] **Step 4: Before deploying to the existing PythonAnywhere host:** set `DEPLOY_REPO_DIR` and `DEPLOY_RELOAD_FILE` in its `.env`, or auto-deploy stops after this change lands.
