import logging

from backend.banks.santander import (
    fetch_transactions as fetch_santander,
    save_last_run_date as save_santander_last_run,
)
from backend.db.storage import init_db, insert_transactions, get_summary

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def main():

    init_db()

    logger.info("Fetching Santander transactions...")
    transactions = fetch_santander()

    if transactions:
        inserted = insert_transactions(transactions)
        save_santander_last_run()
        logger.info(
            f"\n{inserted} new transaction(s) saved ({len(transactions) - inserted} duplicates skipped)"
        )
    else:
        logger.warning("\nNo transactions to save.")

    summary = get_summary()
    if summary:
        logger.info("\nSummary:")
        for tx_type, data in summary.items():
            print(
                f"  {tx_type}: {data['count']} transactions, ${data['total']:,.2f} MXN"
            )


if __name__ == "__main__":
    main()
