import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.constants import (
    CURRENCY_MXN,
    DB_PATH,
    DEFAULT_CATEGORY,
    TX_TYPE_PURCHASE,
    TX_TYPE_TRANSFER,
    TX_TYPE_OUTGOING_TRANSFER,
    UPDATABLE_FIELDS
)


def _end_of_day(date_str: str) -> str:
    """If date_str is date-only (YYYY-MM-DD), append T23:59:59 so that
    '<=' comparisons include all timestamps within that day."""
    if date_str and "T" not in date_str:
        return date_str + "T23:59:59"
    return date_str


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def _connection():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with _connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank TEXT NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'MXN',
                date TEXT NOT NULL,
                merchant TEXT,
                card_last4 TEXT,
                account_last4 TEXT,
                dest_account_last4 TEXT,
                dest_bank TEXT,
                sender_bank TEXT,
                source_account TEXT,
                tracking_key TEXT,
                concept TEXT,
                reference TEXT,
                person TEXT,
                category TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_dedup
            ON transactions (bank, type, amount, date,
                COALESCE(merchant, ''), COALESCE(reference, ''), COALESCE(tracking_key, ''))
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON transactions (type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON transactions (date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bank ON transactions (bank)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON transactions (category)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)


def insert_transactions(transactions: list[dict]) -> int:
    """Inserts transactions, skipping duplicates. Returns count of new rows inserted."""
    with _connection() as conn:
        inserted = 0
        for tx in transactions:
            try:
                conn.execute(
                    """
                    INSERT INTO transactions
                        (bank, type, amount, currency, date, merchant, card_last4,
                         account_last4, dest_account_last4, dest_bank, sender_bank,
                         source_account, tracking_key, concept, reference, person,
                         category, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        tx["bank"],
                        tx["type"],
                        tx["amount"],
                        tx.get("currency", CURRENCY_MXN),
                        tx["date"],
                        tx.get("merchant"),
                        tx.get("card_last4"),
                        tx.get("account_last4"),
                        tx.get("dest_account_last4"),
                        tx.get("dest_bank"),
                        tx.get("sender_bank"),
                        tx.get("source_account"),
                        tx.get("tracking_key"),
                        tx.get("concept"),
                        tx.get("reference"),
                        tx.get("person"),
                        tx.get("category"),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass
        return inserted


def get_transactions(
    bank: str | None = None,
    tx_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    person: str | None = None,
) -> list[dict]:
    """Queries transactions with optional filters."""
    with _connection() as conn:
        query = "SELECT * FROM transactions WHERE 1=1"
        params = []

        if bank:
            query += " AND bank = ?"
            params.append(bank)
        if tx_type:
            query += " AND type = ?"
            params.append(tx_type)
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(_end_of_day(end_date))
        if person:
            query += " AND person = ?"
            params.append(person)

        query += " ORDER BY date DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_summary(start_date: str | None = None, end_date: str | None = None) -> dict:
    """Returns spending summary grouped by type."""
    with _connection() as conn:
        query = """
            SELECT type, COUNT(*) as count, SUM(amount) as total
            FROM transactions WHERE 1=1
        """
        params = []
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(_end_of_day(end_date))
        query += " GROUP BY type"

        rows = conn.execute(query, params).fetchall()
        return {row["type"]: {"count": row["count"], "total": row["total"]} for row in rows}


def get_uncategorized() -> list[dict]:
    """Returns all transactions that have no category assigned."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE category IS NULL ORDER BY date DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def update_categories(updates: list[dict]) -> int:
    """Updates category for a list of transactions. Each dict must have 'id' and 'category'.
    Returns count of rows updated."""
    with _connection() as conn:
        updated = 0
        for item in updates:
            category = item["category"].upper() if item["category"] else None
            result = conn.execute(
                "UPDATE transactions SET category = ? WHERE id = ?",
                (category, item["id"]),
            )
            updated += result.rowcount
        return updated


def get_categories() -> list[str]:
    with _connection() as conn:
        rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
        return [row["name"] for row in rows]


def create_category(name: str) -> str:
    """Creates a category if it doesn't exist. Returns the name (uppercased)."""
    name = name.upper()
    with _connection() as conn:
        try:
            conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        except sqlite3.IntegrityError:
            pass
        return name

def update_transaction(tx_id: int, fields: dict) -> bool:
    """Updates allowed fields for a transaction. Returns True if row was found."""
    to_update = {k: v for k, v in fields.items() if k in UPDATABLE_FIELDS}
    if not to_update:
        return False
    if "category" in to_update and to_update["category"]:
        to_update["category"] = to_update["category"].upper()
    set_clause = ", ".join(f"{k} = ?" for k in to_update)
    values = list(to_update.values()) + [tx_id]
    with _connection() as conn:
        result = conn.execute(
            f"UPDATE transactions SET {set_clause} WHERE id = ?", values
        )
        return result.rowcount > 0


def delete_transaction(tx_id: int) -> bool:
    """Deletes a transaction by ID. Returns True if row was found."""
    with _connection() as conn:
        result = conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
        return result.rowcount > 0


def get_monthly_totals(
    start_date: str | None = None, end_date: str | None = None
) -> list[dict]:
    """Returns totals grouped by month and type."""
    with _connection() as conn:
        query = """
            SELECT SUBSTR(date, 1, 7) as month, type, SUM(amount) as total, COUNT(*) as count
            FROM transactions WHERE 1=1
        """
        params = []
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(_end_of_day(end_date))
        query += " GROUP BY month, type ORDER BY month"
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_merchant_totals(
    start_date: str | None = None, end_date: str | None = None
) -> list[dict]:
    """Returns merchants sorted by total spend (purchases only)."""
    with _connection() as conn:
        query = """
            SELECT merchant, SUM(amount) as total, COUNT(*) as count
            FROM transactions
            WHERE type = ? AND merchant IS NOT NULL
        """
        params = [TX_TYPE_PURCHASE]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(_end_of_day(end_date))
        query += " GROUP BY merchant ORDER BY total DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_breakdown(month: str) -> dict:
    """Returns income/expense breakdown by category for a given month (YYYY-MM)."""
    with _connection() as conn:
        income_rows = conn.execute(
            """
            SELECT COALESCE(UPPER(category), ?) as category, SUM(amount) as total
            FROM transactions
            WHERE type = ? AND SUBSTR(date, 1, 7) = ?
            GROUP BY COALESCE(UPPER(category), ?) ORDER BY total DESC
        """,
            (DEFAULT_CATEGORY, TX_TYPE_TRANSFER, month, DEFAULT_CATEGORY),
        ).fetchall()

        expense_rows = conn.execute(
            """
            SELECT COALESCE(UPPER(category), ?) as category, SUM(amount) as total
            FROM transactions
            WHERE type IN (?, ?) AND SUBSTR(date, 1, 7) = ?
            GROUP BY COALESCE(UPPER(category), ?) ORDER BY total DESC
        """,
            (
                DEFAULT_CATEGORY,
                TX_TYPE_PURCHASE,
                TX_TYPE_OUTGOING_TRANSFER,
                month,
                DEFAULT_CATEGORY,
            ),
        ).fetchall()

        return {
            "income": [dict(r) for r in income_rows],
            "expenses": [dict(r) for r in expense_rows],
        }


def get_savings(year: int) -> list[dict]:
    """Returns monthly savings (income - expenses) for a given year."""
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT SUBSTR(date, 1, 7) as month,
                   SUM(CASE WHEN type = ? THEN amount ELSE 0 END) as income,
                   SUM(CASE WHEN type = ? THEN amount ELSE 0 END) as purchases,
                   SUM(CASE WHEN type = ? THEN amount ELSE 0 END) as outgoing
            FROM transactions
            WHERE date >= ? AND date < ?
            GROUP BY month
            ORDER BY month
        """,
            (
                TX_TYPE_TRANSFER,
                TX_TYPE_PURCHASE,
                TX_TYPE_OUTGOING_TRANSFER,
                f"{year}-01-01",
                f"{year + 1}-01-01",
            ),
        ).fetchall()

        result = []
        for row in rows:
            r = dict(row)
            r["savings"] = r["income"] - r["purchases"] - r["outgoing"]
            result.append(r)
        return result
