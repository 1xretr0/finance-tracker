# Contributing

This is a small personal tool, so keep changes simple and focused.

## Setup and tests

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v
```

Tests must not need network access or real credentials. Test data is inline strings in the test files (no fixture files), and Gmail/HTTP calls are mocked.

## Adding a bank

1. Create `backend/banks/<bank_name>.py` exposing:

   ```python
   def fetch_transactions(since_epoch: int | None = None, interactive: bool = True) -> list[dict]:
   ```

   - It pages through the source's full result set itself (no fixed cap).
   - `since_epoch` is the fetch cursor (`None` means everything).
   - `interactive=False` must never open a browser or block on user input. Raise an error instead (see `AuthenticationRequiredError` in `backend/banks/santander.py`); the server passes `False` when running `POST /api/sync`.
2. Each returned dict needs at least `bank`, `type`, `amount`, `currency` and `date`. Bank names go in `backend/constants.py` (`BANKS_SET`), types are `purchase`, `transfer` or `outgoing_transfer`.
3. Register the source in `SOURCE_BANKS` (`backend/constants.py`), mapping the source name to the `bank` values your parsers write. `process_transactions` uses it to derive each source's fetch cursor from the newest stored transaction.
4. Wire the fetcher into `run_sync` in `backend/process_transactions.py`.
5. Add tests with inline email strings, following `tests/test_santander_parser.py`. Use made-up data only: no real account numbers, names or addresses.

Internal-transfer filtering is not done in bank modules; it lives in `insert_transactions` (storage layer).

## Conventions

- Never commit `.env`, `credentials.json`, `token.json` or any `*.db` file.
- Frontend JS that touches `/api/*` goes through `apiFetch()`/`fetchJSON()` in `frontend/js/common.js`, never raw `fetch()`.
- Anything rendered through `innerHTML` must go through `escapeHTML()` first.
- The dashboard is dark mode: no white backgrounds.
