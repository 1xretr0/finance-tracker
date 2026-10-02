# ---------------------------------------------------------------------------
# Transaction ingestion orchestrator
# ---------------------------------------------------------------------------
import logging
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from backend.banks.santander import fetch_transactions as fetch_santander
from backend.db.storage import init_db, insert_transactions_detailed, get_summary, get_latest_tx_date
from backend.constants import API_TOKEN, REMOTE_API_URL, SOURCE_BANKS, SYNC_OVERLAP_HOURS

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

ZERO_RESULT = {"inserted": 0, "ignored": 0, "duplicates": 0}

# ---------------------------------------------------------------------------
# Storage sinks
# ---------------------------------------------------------------------------
def push_transactions_detailed(transactions: list[dict]) -> dict:
    """Sends transactions to the hosted API instead of writing to a local DB.
    Returns {"inserted", "ignored", "duplicates"} counts: 201 is a newly
    created row, 200 is an internal transfer the server matched against an
    ignored-transfer rule (see api_create_transaction), and 409 is a
    duplicate — both of the latter are expected and skipped, not raised."""
    inserted = ignored = duplicates = 0
    for tx in transactions:
        res = requests.post(
            f"{REMOTE_API_URL}/api/transactions",
            json=tx,
            headers={"Authorization": f"Bearer {API_TOKEN}"},
        )
        if res.status_code == 201:
            inserted += 1
        elif res.status_code == 200:
            ignored += 1
        elif res.status_code == 409:
            duplicates += 1
        else:
            res.raise_for_status()
    return {"inserted": inserted, "ignored": ignored, "duplicates": duplicates}


def push_transactions(transactions: list[dict]) -> int:
    """Sends transactions to the hosted API instead of writing to a local DB.
    Duplicates (409) are treated as expected and skipped. Returns count of
    newly created rows. See push_transactions_detailed for a breakdown of why
    the rest were skipped."""
    return push_transactions_detailed(transactions)["inserted"]

# ---------------------------------------------------------------------------
# Ingestion cursor — derived from the DB instead of a per-client last-run file
# ---------------------------------------------------------------------------
def _compute_since(latest_iso: str | None) -> int | None:
    """Converts the newest stored transaction's ISO date for a source into a
    Gmail `after:` epoch, pulled back by SYNC_OVERLAP_HOURS so a message that
    lands mid-run (or in a gap an earlier overlap missed) is still re-queried
    — duplicates are deduped by the DB's unique index, so widening this is
    safe. Returns None (fetch the whole label) when there's no prior data."""
    if latest_iso is None:
        return None
    latest = datetime.fromisoformat(latest_iso).replace(tzinfo=ZoneInfo("America/Mexico_City"))
    since = latest - timedelta(hours=SYNC_OVERLAP_HOURS)
    return int(since.timestamp())


def get_latest_date(source: str) -> str | None:
    """Returns the newest stored transaction date for `source`: read from the
    local DB, or — when REMOTE_API_URL is set — from the hosted /api/status,
    since the DB that matters for dedup lives on the server in that mode.
    Raises on an unreachable/erroring server so the caller can abort the run
    instead of silently falling back to a full refetch."""
    if REMOTE_API_URL:
        res = requests.get(
            f"{REMOTE_API_URL}/api/status",
            headers={"Authorization": f"Bearer {API_TOKEN}"},
        )
        res.raise_for_status()
        return res.json()["latest_tx_dates"].get(source)
    return get_latest_tx_date(SOURCE_BANKS[source])

# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------
def run_sync(use_remote: bool) -> dict | None:
    """Fetches and stores new Santander transactions since the DB-derived
    cursor. Returns {"inserted", "ignored", "duplicates"} (zero counts if
    nothing new was found) on success, or None if the cursor lookup, fetch,
    or save step failed — callers must treat None as a failed run, distinct
    from a legitimate empty result."""
    try:
        since_epoch = _compute_since(get_latest_date("santander"))
    except Exception:
        logger.exception("Failed to read last sync date")
        return None

    try:
        logger.info("Fetching Santander transactions...")
        transactions = fetch_santander(since_epoch)
    except Exception:
        logger.exception("Failed to fetch Santander transactions")
        return None

    if not transactions:
        logger.warning("No transactions to save.")
        return dict(ZERO_RESULT)

    try:
        if use_remote:
            logger.info(f"Pushing transactions to {REMOTE_API_URL}...")
            result = push_transactions_detailed(transactions)
        else:
            result = insert_transactions_detailed(transactions)
        logger.info(
            f"{result['inserted']} new transaction(s) saved "
            f"({result['duplicates']} duplicates skipped, "
            f"{result['ignored']} internal transfers ignored)"
        )
        return result
    except Exception:
        logger.exception("Failed to save transactions")
        return None


def main():
    use_remote = bool(REMOTE_API_URL)
    if not use_remote:
        init_db()

    if run_sync(use_remote) is None:
        sys.exit(1)

    if not use_remote:
        summary = get_summary()
        if summary:
            logger.info("Summary:")
            for tx_type, data in summary.items():
                logger.info(
                    f"  {tx_type}: {data['count']} transactions, ${data['total']:,.2f} MXN"
                )

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
