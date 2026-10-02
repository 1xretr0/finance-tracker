# ---------------------------------------------------------------------------
# SQLite storage layer for transaction data
# ---------------------------------------------------------------------------
import sqlite3
import statistics
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.constants import (
    CURRENCY_MXN,
    DB_PATH,
    DEFAULT_CATEGORY,
    IGNORED_ACCOUNT_TRANSFERS,
    SOURCE_BANKS,
    TX_TYPE_PURCHASE,
    TX_TYPE_TRANSFER,
    TX_TYPE_OUTGOING_TRANSFER,
    UPDATABLE_FIELDS
)

# ---------------------------------------------------------------------------
# Database connection management
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------
def _end_of_day(date_str: str) -> str:
    """If date_str is date-only (YYYY-MM-DD), append T23:59:59 so that
    '<=' comparisons include all timestamps within that day."""
    if date_str and "T" not in date_str:
        return date_str + "T23:59:59"
    return date_str


def _add_column_if_missing(conn: sqlite3.Connection, table: str, col: str, decl: str) -> bool:
    """Adds `col` to `table` if it doesn't already exist. Returns True if the
    column was just added (so callers can run a one-time backfill), False if
    it already existed (or a concurrent caller added it first — see below)."""
    cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if col in cols:
        return False
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    except sqlite3.OperationalError as e:
        # Lost a race with a concurrent first boot that added this column
        # between our PRAGMA check and this ALTER (no lock spans the two on
        # SQLite, and a lock in server.py only covers one process/worker).
        # The column exists now regardless of who won, so treat it as a
        # no-op rather than propagating a spurious 500.
        if "duplicate column name" in str(e).lower():
            return False
        raise
    return True


def _backfill_category_kinds(conn: sqlite3.Connection) -> None:
    """One-time backfill run when the `kind` column is first added: infers
    each category's kind from how its transactions have been used so far.
    Categories used for both income and expenses (or not used at all) are
    left NULL rather than guessed."""
    rows = conn.execute(
        """
        SELECT UPPER(category) as category,
               SUM(CASE WHEN type = ? THEN 1 ELSE 0 END) as income_count,
               SUM(CASE WHEN type IN (?, ?) THEN 1 ELSE 0 END) as expense_count
        FROM transactions
        WHERE category IS NOT NULL
        GROUP BY UPPER(category)
        """,
        (TX_TYPE_TRANSFER, TX_TYPE_PURCHASE, TX_TYPE_OUTGOING_TRANSFER),
    ).fetchall()

    for row in rows:
        if row["income_count"] and not row["expense_count"]:
            kind = "income"
        elif row["expense_count"] and not row["income_count"]:
            kind = "expense"
        else:
            continue
        conn.execute("UPDATE categories SET kind = ? WHERE name = ?", (kind, row["category"]))

# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------
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
                notes TEXT,
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
                name TEXT NOT NULL UNIQUE,
                kind TEXT,
                budget REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ignored_transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_last4 TEXT NOT NULL,
                bank TEXT NOT NULL
            )
        """)

        # ---- Migrations for DBs created before these columns existed ----
        _add_column_if_missing(conn, "transactions", "notes", "TEXT")
        kind_added = _add_column_if_missing(conn, "categories", "kind", "TEXT")
        _add_column_if_missing(conn, "categories", "budget", "REAL")
        if kind_added:
            _backfill_category_kinds(conn)

        # One-time cleanup for DBs created before the unique index below
        # existed, where a lost seeding race (or a duplicate manual add)
        # could have left more than one row per (account_last4, bank).
        conn.execute("""
            DELETE FROM ignored_transfers WHERE id NOT IN (
                SELECT MIN(id) FROM ignored_transfers GROUP BY account_last4, LOWER(bank))
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ignored_transfers_unique
            ON ignored_transfers (account_last4, bank COLLATE NOCASE)
        """)

        if conn.execute("SELECT COUNT(*) as n FROM ignored_transfers").fetchone()["n"] == 0:
            for rule in IGNORED_ACCOUNT_TRANSFERS:
                conn.execute(
                    "INSERT OR IGNORE INTO ignored_transfers (account_last4, bank) VALUES (?, ?)",
                    (rule["account_last4"], rule["bank"]),
                )

# ---------------------------------------------------------------------------
# Internal transfer filtering
# ---------------------------------------------------------------------------
def _ignore_check_fields(tx: dict) -> tuple[str | None, str | None]:
    """Returns the (account, bank) pair relevant to ignore-rule matching for
    tx's type, or (None, None) for types that can't be internal transfers."""
    if tx.get("type") == TX_TYPE_TRANSFER:
        return tx.get("source_account"), tx.get("sender_bank")
    if tx.get("type") == TX_TYPE_OUTGOING_TRANSFER:
        return tx.get("dest_account_last4"), tx.get("dest_bank")
    return None, None


def is_ignored_transfer(tx: dict, conn: sqlite3.Connection | None = None) -> bool:
    """Checks whether tx is an internal transfer between the user's own
    accounts, per the rules in the `ignored_transfers` table (seeded from
    IGNORED_ACCOUNT_TRANSFERS, editable via /settings)."""
    account, bank = _ignore_check_fields(tx)
    if not account or not bank:
        return False
    if conn is None:
        with _connection() as new_conn:
            return is_ignored_transfer(tx, new_conn)
    row = conn.execute(
        "SELECT 1 FROM ignored_transfers WHERE account_last4 = ? AND LOWER(bank) = LOWER(?)",
        (str(account)[-4:], bank),
    ).fetchone()
    return row is not None

# ---------------------------------------------------------------------------
# Transaction insert operations
# ---------------------------------------------------------------------------
def insert_transactions_detailed(transactions: list[dict]) -> dict:
    """Inserts transactions, skipping duplicates and internal transfers
    between the user's own accounts (see is_ignored_transfer). Returns
    {"inserted", "ignored", "duplicates"} counts, so callers that need to
    log or report them separately (e.g. process_transactions.py) don't have
    to lump ignored transfers in with real duplicates."""
    with _connection() as conn:
        inserted = ignored = duplicates = 0
        for tx in transactions:
            if is_ignored_transfer(tx, conn):
                ignored += 1
                continue
            try:
                conn.execute(
                    """
                    INSERT INTO transactions
                        (bank, type, amount, currency, date, merchant, card_last4,
                         account_last4, dest_account_last4, dest_bank, sender_bank,
                         source_account, tracking_key, concept, reference, person,
                         category, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        tx.get("notes"),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                duplicates += 1
        return {"inserted": inserted, "ignored": ignored, "duplicates": duplicates}


def insert_transactions(transactions: list[dict]) -> int:
    """Inserts transactions, skipping duplicates and internal transfers
    between the user's own accounts (see is_ignored_transfer). Returns count
    of new rows inserted. See insert_transactions_detailed for a breakdown
    of why the rest were skipped."""
    return insert_transactions_detailed(transactions)["inserted"]

# ---------------------------------------------------------------------------
# Transaction query operations
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Category management
# ---------------------------------------------------------------------------
def _description_key(tx: dict) -> str | None:
    """The field used to recognize 'the same transaction description' across
    rows, for category suggestions and recurring-expense detection."""
    return tx.get("merchant") or tx.get("dest_bank") or tx.get("sender_bank") or tx.get("concept")


def _suggest_category(conn: sqlite3.Connection, key: str) -> str | None:
    """The category most often used for other already-categorized
    transactions sharing the same description key."""
    row = conn.execute(
        """
        SELECT category, COUNT(*) as cnt
        FROM transactions
        WHERE category IS NOT NULL
          AND COALESCE(merchant, dest_bank, sender_bank, concept) = ?
        GROUP BY category
        ORDER BY cnt DESC
        LIMIT 1
        """,
        (key,),
    ).fetchone()
    return row["category"] if row else None


def get_uncategorized() -> list[dict]:
    """Returns all transactions that have no category assigned, each with an
    additive `suggested_category` inferred from how other transactions with
    the same merchant/sender/concept were categorized previously."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE category IS NULL ORDER BY date DESC"
        ).fetchall()
        result = []
        for row in rows:
            tx = dict(row)
            key = _description_key(tx)
            tx["suggested_category"] = _suggest_category(conn, key) if key else None
            result.append(tx)
        return result


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


def get_categories(detailed: bool = False) -> list[str] | list[dict]:
    """Returns category names, or (when detailed=True) full rows with kind,
    budget and how many transactions currently use each category."""
    with _connection() as conn:
        if not detailed:
            rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
            return [row["name"] for row in rows]

        rows = conn.execute(
            """
            SELECT c.id, c.name, c.kind, c.budget,
                   (SELECT COUNT(*) FROM transactions t WHERE t.category = c.name) as count
            FROM categories c
            ORDER BY c.name
            """
        ).fetchall()
        return [dict(row) for row in rows]


def create_category(name: str, kind: str | None = None) -> str:
    """Creates a category if it doesn't exist. Returns the name (uppercased)."""
    name = name.upper()
    with _connection() as conn:
        try:
            conn.execute("INSERT INTO categories (name, kind) VALUES (?, ?)", (name, kind))
        except sqlite3.IntegrityError:
            pass
        return name


def update_category(cat_id: int, fields: dict) -> dict | None:
    """Updates a category's name, kind and/or budget. Renaming onto a name
    that already exists merges the two categories: transactions move to the
    existing target and the source row is removed. Resolves rename/merge
    first, then applies kind/budget to whichever row survives, so a merge
    never silently drops a kind/budget update made in the same call. Returns
    the resulting category row, or None if cat_id doesn't exist."""
    with _connection() as conn:
        row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if not row:
            return None
        current_name = row["name"]
        target_id = cat_id

        raw_name = fields.get("name")
        new_name = raw_name.strip().upper() if isinstance(raw_name, str) else None
        if new_name and new_name != current_name:
            existing = conn.execute(
                "SELECT id FROM categories WHERE name = ?", (new_name,)
            ).fetchone()
            conn.execute(
                "UPDATE transactions SET category = ? WHERE category = ?",
                (new_name, current_name),
            )
            if existing:
                conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
                target_id = existing["id"]
            else:
                conn.execute("UPDATE categories SET name = ? WHERE id = ?", (new_name, cat_id))

        if "kind" in fields:
            conn.execute("UPDATE categories SET kind = ? WHERE id = ?", (fields["kind"], target_id))
        if "budget" in fields:
            conn.execute("UPDATE categories SET budget = ? WHERE id = ?", (fields["budget"], target_id))

        return dict(conn.execute("SELECT * FROM categories WHERE id = ?", (target_id,)).fetchone())


def delete_category(cat_id: int) -> bool:
    """Deletes a category. Transactions that used it become uncategorized
    again (category set to NULL) rather than being deleted. Returns True if
    the category existed."""
    with _connection() as conn:
        row = conn.execute("SELECT name FROM categories WHERE id = ?", (cat_id,)).fetchone()
        if not row:
            return False
        conn.execute("UPDATE transactions SET category = NULL WHERE category = ?", (row["name"],))
        conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        return True

# ---------------------------------------------------------------------------
# User authentication
# ---------------------------------------------------------------------------
def get_user(username: str) -> dict | None:
    """Looks up a user by username. Users are added directly to the DB
    (no signup flow); this only validates against existing rows."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None

# ---------------------------------------------------------------------------
# Transaction update & delete operations
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Aggregation & reporting queries
# ---------------------------------------------------------------------------
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


def get_breakdown(month: str | None = None, year: str | None = None) -> dict:
    """Returns income/expense breakdown by category for a given month
    (YYYY-MM) or, if `year` (YYYY) is given instead, for the whole year."""
    period = year if year else month
    period_len = 4 if year else 7
    with _connection() as conn:
        income_rows = conn.execute(
            """
            SELECT COALESCE(UPPER(category), ?) as category, SUM(amount) as total
            FROM transactions
            WHERE type = ? AND SUBSTR(date, 1, ?) = ?
            GROUP BY COALESCE(UPPER(category), ?) ORDER BY total DESC
        """,
            (DEFAULT_CATEGORY, TX_TYPE_TRANSFER, period_len, period, DEFAULT_CATEGORY),
        ).fetchall()

        expense_rows = conn.execute(
            """
            SELECT COALESCE(UPPER(category), ?) as category, SUM(amount) as total
            FROM transactions
            WHERE type IN (?, ?) AND SUBSTR(date, 1, ?) = ?
            GROUP BY COALESCE(UPPER(category), ?) ORDER BY total DESC
        """,
            (
                DEFAULT_CATEGORY,
                TX_TYPE_PURCHASE,
                TX_TYPE_OUTGOING_TRANSFER,
                period_len,
                period,
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
            SELECT 
                SUBSTR(date, 1, 7) as month,
                IFNULL((SELECT SUM(amount) FROM transactions WHERE type = ? AND SUBSTR(date, 1, 7) <= SUBSTR(main.date, 1, 7)), 0) AS total_income,
                IFNULL((SELECT SUM(amount) FROM transactions WHERE (type = ? OR type = ?) AND SUBSTR(date, 1, 7) <= SUBSTR(main.date, 1, 7)), 0) AS total_outcome,
                SUM(CASE WHEN type = ? THEN amount ELSE 0 END) as income,
                SUM(CASE WHEN type = ? THEN amount ELSE 0 END) as purchases,
                SUM(CASE WHEN type = ? THEN amount ELSE 0 END) as outgoing
            FROM 
                transactions main
            WHERE 
                date >= ? AND 
                date < ?
            GROUP BY month
            ORDER BY month
        """,
            (
                TX_TYPE_TRANSFER,
                TX_TYPE_PURCHASE,
                TX_TYPE_OUTGOING_TRANSFER,
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
            r["total_savings"] = r["total_income"] - r["total_outcome"]
            result.append(r)
        return result


def _shifted_month(month: str, delta: int) -> str:
    y, m = (int(p) for p in month.split("-"))
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _longest_consecutive_run(seen_months: set[str], all_months: list[str]) -> int:
    longest = current = 0
    for mon in all_months:
        if mon in seen_months:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def get_recurring(month: str) -> list[dict]:
    """Detects recurring expenses: merchants (or transfer destinations) that
    appear in 3+ consecutive months within the 6 leading up to `month`, with
    monthly totals staying within +/-20% of their median. Returns each
    merchant's typical amount, the date last seen, and how many of those 6
    months it appeared in."""
    months = [_shifted_month(month, -i) for i in range(5, -1, -1)]

    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(merchant, dest_bank) as merchant, amount, date
            FROM transactions
            WHERE type IN (?, ?)
              AND COALESCE(merchant, dest_bank) IS NOT NULL
              AND SUBSTR(date, 1, 7) >= ? AND SUBSTR(date, 1, 7) <= ?
            """,
            (TX_TYPE_PURCHASE, TX_TYPE_OUTGOING_TRANSFER, months[0], months[-1]),
        ).fetchall()

    by_merchant = defaultdict(lambda: defaultdict(float))
    last_date = {}
    for row in rows:
        key, mon = row["merchant"], row["date"][:7]
        by_merchant[key][mon] += row["amount"]
        if key not in last_date or row["date"] > last_date[key]:
            last_date[key] = row["date"]

    results = []
    for merchant, month_totals in by_merchant.items():
        seen = set(month_totals.keys())
        if len(seen) < 3 or _longest_consecutive_run(seen, months) < 3:
            continue
        totals = list(month_totals.values())
        median = statistics.median(totals)
        if median <= 0 or any(abs(t - median) > median * 0.2 for t in totals):
            continue
        results.append({
            "merchant": merchant,
            "typical_amount": median,
            "last_date": last_date[merchant],
            "months_seen": len(seen),
        })

    results.sort(key=lambda r: r["typical_amount"], reverse=True)
    return results

# ---------------------------------------------------------------------------
# Settings (key/value store for savings goal, etc.)
# ---------------------------------------------------------------------------
def get_setting(key: str) -> str | None:
    with _connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_setting(key: str, value) -> None:
    """Sets a setting, or clears it if value is None."""
    with _connection() as conn:
        if value is None:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        else:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )

# ---------------------------------------------------------------------------
# Ignored transfer rules (internal transfers between the user's own accounts)
# ---------------------------------------------------------------------------
def get_ignored_transfers() -> list[dict]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM ignored_transfers ORDER BY bank, account_last4"
        ).fetchall()
        return [dict(row) for row in rows]


def create_ignored_transfer(account_last4: str, bank: str) -> dict:
    """Creates a rule, or returns the existing one if it already exists
    (same account_last4, bank case-insensitive) — the unique index on
    ignored_transfers makes this idempotent instead of raising."""
    with _connection() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO ignored_transfers (account_last4, bank) VALUES (?, ?)",
            (account_last4, bank),
        )
        if cur.rowcount == 0:
            row = conn.execute(
                "SELECT * FROM ignored_transfers WHERE account_last4 = ? AND bank = ? COLLATE NOCASE",
                (account_last4, bank),
            ).fetchone()
            return dict(row)
        return {"id": cur.lastrowid, "account_last4": account_last4, "bank": bank}


def delete_ignored_transfer(rule_id: int) -> bool:
    with _connection() as conn:
        result = conn.execute("DELETE FROM ignored_transfers WHERE id = ?", (rule_id,))
        return result.rowcount > 0

# ---------------------------------------------------------------------------
# Sync / data-freshness status
# ---------------------------------------------------------------------------
def get_status() -> dict:
    """Reports when the DB was last written to by ingestion (excluding
    manually-created transactions, whose `reference` is 'MAN-<epoch>-<rand>'
    per the frontend's generateReference()) and how many transactions still
    need a category."""
    with _connection() as conn:
        last_synced = conn.execute(
            "SELECT MAX(created_at) as last FROM transactions "
            "WHERE reference IS NULL OR reference NOT LIKE 'MAN-%'"
        ).fetchone()["last"]
        uncategorized = conn.execute(
            "SELECT COUNT(*) as cnt FROM transactions WHERE category IS NULL"
        ).fetchone()["cnt"]
        latest_tx_dates = {
            source: get_latest_tx_date(banks) for source, banks in SOURCE_BANKS.items()
        }
        return {
            "last_synced": last_synced,
            "uncategorized": uncategorized,
            "latest_tx_dates": latest_tx_dates,
        }


def get_latest_tx_date(banks: list[str]) -> str | None:
    """Returns the most recent `date` among transactions for the given banks,
    used by process_transactions.py to derive each ingestion source's Gmail
    cursor instead of a per-client last-run file. Excludes manually-created
    transactions (see get_status) so a manual entry can't advance the cursor
    past emails that were never actually ingested."""
    if not banks:
        return None
    with _connection() as conn:
        placeholders = ",".join("?" * len(banks))
        row = conn.execute(
            f"SELECT MAX(date) as latest FROM transactions "
            f"WHERE bank IN ({placeholders}) "
            f"AND (reference IS NULL OR reference NOT LIKE 'MAN-%')",
            banks,
        ).fetchone()
        return row["latest"]
