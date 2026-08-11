# ---------------------------------------------------------------------------
# Transaction ingestion orchestrator
# ---------------------------------------------------------------------------
import logging

import requests

from backend.banks.santander import (
    fetch_transactions as fetch_santander,
    save_last_run_date as save_santander_last_run,
)
from backend.db.storage import init_db, insert_transactions, get_summary
from backend.constants import API_TOKEN, REMOTE_API_URL

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Storage sinks
# ---------------------------------------------------------------------------
def push_transactions(transactions: list[dict]) -> int:
    """Sends transactions to the hosted API instead of writing to a local DB.
    Duplicates (409) are treated as expected and skipped. Returns count of
    newly created rows."""
    inserted = 0
    for tx in transactions:
        res = requests.post(
            f"{REMOTE_API_URL}/api/transactions",
            json=tx,
            headers={"Authorization": f"Bearer {API_TOKEN}"},
        )
        if res.status_code == 201:
            inserted += 1
        elif res.status_code == 409:
            continue
        else:
            res.raise_for_status()
    return inserted

# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------
def main():
    use_remote = bool(REMOTE_API_URL)
    if not use_remote:
        init_db()

    try:
        logger.info("Fetching Santander transactions...")
        transactions = fetch_santander()
    except Exception as e:
        logger.error(f"Failed to fetch Santander transactions: {e}")
        return

    if transactions:
        try:
            if use_remote:
                logger.info(f"Pushing transactions to {REMOTE_API_URL}...")
                inserted = push_transactions(transactions)
            else:
                inserted = insert_transactions(transactions)
            save_santander_last_run()
            logger.info(
                f"{inserted} new transaction(s) saved ({len(transactions) - inserted} duplicates skipped)"
            )
        except Exception as e:
            logger.error(f"Failed to save transactions: {e}")
            return
    else:
        logger.warning("No transactions to save.")

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
