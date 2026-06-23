import sqlite3
from datetime import datetime, timezone

from backend.constants import CURRENCY_MXN, DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)
    conn.commit()
    conn.close()


def insert_transactions(transactions: list[dict]) -> int:
    """Inserts transactions, skipping duplicates. Returns count of new rows inserted."""
    conn = get_connection()
    inserted = 0
    for tx in transactions:
        try:
            conn.execute(
                """
                INSERT INTO transactions
                    (bank, type, amount, currency, date, merchant, card_last4,
                     account_last4, dest_account_last4, dest_bank, sender_bank,
                     source_account, tracking_key, concept, reference, person, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    return inserted


def get_transactions(
    bank: str | None = None,
    tx_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    person: str | None = None,
) -> list[dict]:
    """Queries transactions with optional filters."""
    conn = get_connection()
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
        params.append(end_date)
    if person:
        query += " AND person = ?"
        params.append(person)

    query += " ORDER BY date DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_summary(start_date: str | None = None, end_date: str | None = None) -> dict:
    """Returns spending summary grouped by type."""
    conn = get_connection()
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
        params.append(end_date)
    query += " GROUP BY type"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return {row["type"]: {"count": row["count"], "total": row["total"]} for row in rows}


def get_uncategorized() -> list[dict]:
    """Returns all transactions that have no category assigned."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE category IS NULL ORDER BY date DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_categories(updates: list[dict]) -> int:
    """Updates category for a list of transactions. Each dict must have 'id' and 'category'.
    Returns count of rows updated."""
    conn = get_connection()
    updated = 0
    for item in updates:
        category = item["category"].upper() if item["category"] else None
        result = conn.execute(
            "UPDATE transactions SET category = ? WHERE id = ?",
            (category, item["id"]),
        )
        updated += result.rowcount
    conn.commit()
    conn.close()
    return updated


def get_categories() -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    conn.close()
    return [row["name"] for row in rows]


def create_category(name: str) -> str:
    """Creates a category if it doesn't exist. Returns the name (uppercased)."""
    name = name.upper()
    conn = get_connection()
    try:
        conn.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return name
