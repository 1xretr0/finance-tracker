# ---------------------------------------------------------------------------
# Transaction ingestion orchestrator
# ---------------------------------------------------------------------------
import logging

import requests

from backend.banks.santander import (
    fetch_transactions as fetch_santander,
    save_last_run_date as save_santander_last_run,
)
from backend.db.storage import init_db, insert_transactions, insert_transactions_detailed, get_summary
from backend.constants import API_TOKEN, REMOTE_API_URL

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

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
                result = push_transactions_detailed(transactions)
            else:
                result = insert_transactions_detailed(transactions)
            save_santander_last_run()
            logger.info(
                f"{result['inserted']} new transaction(s) saved "
                f"({result['duplicates']} duplicates skipped, "
                f"{result['ignored']} internal transfers ignored)"
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
