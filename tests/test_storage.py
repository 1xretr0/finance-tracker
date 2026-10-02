# ---------------------------------------------------------------------------
# Tests for SQLite storage layer
# ---------------------------------------------------------------------------
import sqlite3

import pytest
from backend.db.storage import (
    init_db, insert_transactions, get_transactions, get_summary, get_connection,
    get_uncategorized, update_categories, get_categories, create_category,
    update_category, delete_category, update_transaction, delete_transaction,
    get_user, get_breakdown, get_recurring, get_setting, set_setting,
    get_ignored_transfers, create_ignored_transfer, delete_ignored_transfer,
    get_status, is_ignored_transfer, _connection, get_latest_tx_date,
)
import backend.db.storage as storage

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    init_db()
    yield db_path

# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------
def make_purchase(amount=100.0, date="2026-06-15T15:01:07", merchant="OXXO"):
    return {
        "bank": "santander",
        "type": "purchase",
        "amount": amount,
        "currency": "MXN",
        "date": date,
        "merchant": merchant,
        "card_last4": "8949",
    }


def make_transfer(amount=5000.0, date="2026-06-12T12:03:00"):
    return {
        "bank": "santander",
        "type": "transfer",
        "amount": amount,
        "currency": "MXN",
        "date": date,
        "account_last4": "6466",
        "sender_bank": "HSBC",
        "source_account": "2893",
        "tracking_key": "HSBC628982",
        "concept": "NOMINA",
    }

# ---------------------------------------------------------------------------
# Test suite: Insert operations
# ---------------------------------------------------------------------------
class TestInsert:
    def test_inserts_single_transaction(self):
        count = insert_transactions([make_purchase()])
        assert count == 1

    def test_inserts_multiple_transactions(self):
        txs = [make_purchase(amount=100), make_purchase(amount=200)]
        count = insert_transactions(txs)
        assert count == 2

    def test_skips_duplicates(self):
        tx = make_purchase()
        insert_transactions([tx])
        count = insert_transactions([tx])
        assert count == 0

    def test_returns_zero_for_empty_list(self):
        count = insert_transactions([])
        assert count == 0

    def test_detailed_counts_inserted_ignored_and_duplicates(self):
        create_ignored_transfer("6184", "Mercado Pago W")
        ignored_tx = make_transfer()
        ignored_tx["source_account"] = "6184"
        ignored_tx["sender_bank"] = "Mercado Pago W"
        dup_tx = make_purchase()

        insert_transactions([dup_tx])  # pre-insert so the second call is a duplicate
        result = storage.insert_transactions_detailed([dup_tx, ignored_tx, make_purchase(amount=999)])

        assert result == {"inserted": 1, "ignored": 1, "duplicates": 1}

    def test_stores_all_fields(self):
        tx = make_transfer()
        insert_transactions([tx])
        rows = get_transactions()
        assert len(rows) == 1
        row = rows[0]
        assert row["sender_bank"] == "HSBC"
        assert row["tracking_key"] == "HSBC628982"
        assert row["concept"] == "NOMINA"

# ---------------------------------------------------------------------------
# Test suite: Query operations
# ---------------------------------------------------------------------------
class TestQuery:
    def test_filter_by_bank(self):
        insert_transactions([make_purchase()])
        rows = get_transactions(bank="santander")
        assert len(rows) == 1
        rows = get_transactions(bank="bbva")
        assert len(rows) == 0

    def test_filter_by_type(self):
        insert_transactions([make_purchase(), make_transfer()])
        rows = get_transactions(tx_type="purchase")
        assert len(rows) == 1
        assert rows[0]["type"] == "purchase"

    def test_filter_by_date_range(self):
        insert_transactions([
            make_purchase(date="2026-06-01T10:00:00"),
            make_purchase(date="2026-06-15T10:00:00", amount=200),
            make_purchase(date="2026-06-30T10:00:00", amount=300),
        ])
        rows = get_transactions(start_date="2026-06-10", end_date="2026-06-20")
        assert len(rows) == 1
        assert rows[0]["amount"] == 200.0

    def test_filter_by_person(self):
        tx = make_purchase()
        tx["person"] = "me"
        insert_transactions([tx])
        assert len(get_transactions(person="me")) == 1
        assert len(get_transactions(person="partner")) == 0

    def test_ordered_by_date_desc(self):
        insert_transactions([
            make_purchase(date="2026-06-01T10:00:00", amount=100),
            make_purchase(date="2026-06-15T10:00:00", amount=200),
        ])
        rows = get_transactions()
        assert rows[0]["date"] > rows[1]["date"]

# ---------------------------------------------------------------------------
# Test suite: Summary & aggregation operations
# ---------------------------------------------------------------------------
class TestSummary:
    def test_groups_by_type(self):
        insert_transactions([
            make_purchase(amount=100),
            make_purchase(amount=200),
            make_transfer(amount=5000),
        ])
        summary = get_summary()
        assert summary["purchase"]["count"] == 2
        assert summary["purchase"]["total"] == 300.0
        assert summary["transfer"]["count"] == 1
        assert summary["transfer"]["total"] == 5000.0

    def test_empty_db_returns_empty_dict(self):
        summary = get_summary()
        assert summary == {}

    def test_summary_with_date_filter(self):
        insert_transactions([
            make_purchase(date="2026-05-01T10:00:00", amount=100),
            make_purchase(date="2026-06-15T10:00:00", amount=200),
        ])
        summary = get_summary(start_date="2026-06-01")
        assert summary["purchase"]["count"] == 1
        assert summary["purchase"]["total"] == 200.0

# ---------------------------------------------------------------------------
# Test suite: Raw SQL queries (verification tests)
# ---------------------------------------------------------------------------
class TestRawSQL:
    """Direct SQL SELECT queries against the database to verify stored records."""

    def test_select_all_records(self):
        insert_transactions([
            make_purchase(amount=150, merchant="STARBUCKS"),
            make_purchase(amount=320, merchant="WALMART"),
            make_transfer(amount=10000),
        ])
        conn = get_connection()
        rows = conn.execute("SELECT bank, type, amount, merchant FROM transactions ORDER BY amount").fetchall()
        print([dict(r) for r in rows])
        conn.close()

        assert len(rows) == 3
        assert dict(rows[0]) == {"bank": "santander", "type": "purchase", "amount": 150.0, "merchant": "STARBUCKS"}
        assert dict(rows[1]) == {"bank": "santander", "type": "purchase", "amount": 320.0, "merchant": "WALMART"}
        assert dict(rows[2]) == {"bank": "santander", "type": "transfer", "amount": 10000.0, "merchant": None}

    def test_select_sum_by_type(self):
        insert_transactions([
            make_purchase(amount=100),
            make_purchase(amount=250),
            make_purchase(amount=75),
            make_transfer(amount=50000),
        ])
        conn = get_connection()
        rows = conn.execute(
            "SELECT type, COUNT(*) as cnt, SUM(amount) as total FROM transactions GROUP BY type ORDER BY type"
        ).fetchall()
        print([dict(r) for r in rows])
        conn.close()

        results = {row["type"]: {"cnt": row["cnt"], "total": row["total"]} for row in rows}
        assert results["purchase"] == {"cnt": 3, "total": 425.0}
        assert results["transfer"] == {"cnt": 1, "total": 50000.0}

    def test_select_with_where_clause(self):
        insert_transactions([
            make_purchase(amount=50, merchant="OXXO", date="2026-06-01T08:00:00"),
            make_purchase(amount=600, merchant="VIPS LEGARIA", date="2026-06-10T13:00:00"),
            make_purchase(amount=120, merchant="OXXO", date="2026-06-20T19:00:00"),
        ])
        conn = get_connection()
        rows = conn.execute(
            "SELECT amount, date FROM transactions WHERE merchant = ? ORDER BY date",
            ("OXXO",)
        ).fetchall()
        print([dict(r) for r in rows])
        conn.close()

        assert len(rows) == 2
        assert rows[0]["amount"] == 50.0
        assert rows[1]["amount"] == 120.0

    def test_select_monthly_spending(self):
        insert_transactions([
            make_purchase(amount=100, date="2026-05-10T10:00:00"),
            make_purchase(amount=200, date="2026-05-20T10:00:00"),
            make_purchase(amount=350, date="2026-06-05T10:00:00"),
            make_purchase(amount=150, date="2026-06-15T10:00:00", merchant="UBER"),
        ])
        conn = get_connection()
        rows = conn.execute("""
            SELECT SUBSTR(date, 1, 7) as month, SUM(amount) as total, COUNT(*) as cnt
            FROM transactions
            WHERE type = 'purchase'
            GROUP BY month
            ORDER BY month
        """).fetchall()
        print([dict(r) for r in rows])
        conn.close()

        assert len(rows) == 2
        assert dict(rows[0]) == {"month": "2026-05", "total": 300.0, "cnt": 2}
        assert dict(rows[1]) == {"month": "2026-06", "total": 500.0, "cnt": 2}

    def test_select_top_merchants_by_spend(self):
        insert_transactions([
            make_purchase(amount=100, merchant="OXXO"),
            make_purchase(amount=200, merchant="OXXO", date="2026-06-16T10:00:00"),
            make_purchase(amount=500, merchant="VIPS LEGARIA", date="2026-06-17T10:00:00"),
            make_purchase(amount=80, merchant="STARBUCKS", date="2026-06-18T10:00:00"),
        ])
        conn = get_connection()
        rows = conn.execute("""
            SELECT merchant, SUM(amount) as total, COUNT(*) as visits
            FROM transactions
            WHERE type = 'purchase'
            GROUP BY merchant
            ORDER BY total DESC
        """).fetchall()
        print([dict(r) for r in rows])
        conn.close()

        assert len(rows) == 3
        assert rows[0]["merchant"] == "VIPS LEGARIA"
        assert rows[0]["total"] == 500.0
        assert rows[1]["merchant"] == "OXXO"
        assert rows[1]["total"] == 300.0
        assert rows[1]["visits"] == 2

    def test_select_transfers_with_full_details(self):
        insert_transactions([make_transfer(amount=25000)])
        conn = get_connection()
        row = conn.execute("""
            SELECT bank, type, amount, account_last4, sender_bank,
                   source_account, tracking_key, concept, date
            FROM transactions
            WHERE type = 'transfer'
        """).fetchone()
        print(dict(row))
        conn.close()

        assert row["amount"] == 25000.0
        assert row["account_last4"] == "6466"
        assert row["sender_bank"] == "HSBC"
        assert row["source_account"] == "2893"
        assert row["tracking_key"] == "HSBC628982"
        assert row["concept"] == "NOMINA"

# ---------------------------------------------------------------------------
# Test suite: Category management operations
# ---------------------------------------------------------------------------
class TestGetUncategorized:
    def test_returns_only_uncategorized(self):
        insert_transactions([make_purchase(merchant="OXXO"), make_purchase(amount=200, merchant="VIPS")])
        rows = get_uncategorized()
        assert len(rows) == 2

    def test_excludes_categorized(self):
        insert_transactions([make_purchase()])
        update_categories([{"id": get_transactions()[0]["id"], "category": "food"}])
        rows = get_uncategorized()
        assert len(rows) == 0

    def test_empty_db_returns_empty_list(self):
        assert get_uncategorized() == []

    def test_ordered_by_date_desc(self):
        insert_transactions([
            make_purchase(date="2026-06-01T10:00:00", amount=100),
            make_purchase(date="2026-06-15T10:00:00", amount=200),
        ])
        rows = get_uncategorized()
        assert rows[0]["date"] > rows[1]["date"]


class TestUpdateCategories:
    def test_updates_category_for_single_transaction(self):
        insert_transactions([make_purchase()])
        tx_id = get_transactions()[0]["id"]
        count = update_categories([{"id": tx_id, "category": "food"}])
        assert count == 1
        assert get_transactions()[0]["category"] == "FOOD"

    def test_uppercases_category(self):
        insert_transactions([make_purchase()])
        tx_id = get_transactions()[0]["id"]
        update_categories([{"id": tx_id, "category": "groceries"}])
        assert get_transactions()[0]["category"] == "GROCERIES"

    def test_sets_category_to_none(self):
        insert_transactions([make_purchase()])
        tx_id = get_transactions()[0]["id"]
        update_categories([{"id": tx_id, "category": "food"}])
        update_categories([{"id": tx_id, "category": None}])
        assert get_transactions()[0]["category"] is None

    def test_updates_multiple_transactions(self):
        insert_transactions([make_purchase(amount=100), make_purchase(amount=200)])
        ids = [tx["id"] for tx in get_transactions()]
        count = update_categories([{"id": ids[0], "category": "food"}, {"id": ids[1], "category": "transport"}])
        assert count == 2

    def test_returns_zero_for_nonexistent_id(self):
        count = update_categories([{"id": 9999, "category": "food"}])
        assert count == 0


class TestGetCategories:
    def test_returns_empty_list_when_none_exist(self):
        assert get_categories() == []

    def test_returns_all_categories_sorted(self):
        create_category("transport")
        create_category("food")
        create_category("utilities")
        cats = get_categories()
        assert cats == ["FOOD", "TRANSPORT", "UTILITIES"]

    def test_returns_list_of_strings(self):
        create_category("health")
        cats = get_categories()
        assert all(isinstance(c, str) for c in cats)


class TestCreateCategory:
    def test_creates_and_uppercases_category(self):
        name = create_category("groceries")
        assert name == "GROCERIES"
        assert "GROCERIES" in get_categories()

    def test_ignores_duplicate(self):
        create_category("food")
        create_category("food")
        assert get_categories().count("FOOD") == 1

    def test_already_uppercased_input(self):
        name = create_category("TRANSPORT")
        assert name == "TRANSPORT"
        assert "TRANSPORT" in get_categories()

# ---------------------------------------------------------------------------
# Test suite: User authentication
# ---------------------------------------------------------------------------
class TestGetUser:
    def _insert_user(self, username="sebas", password_hash="hashed"):
        with _connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, "2026-01-01T00:00:00"),
            )

    def test_returns_none_for_unknown_user(self):
        assert get_user("nobody") is None

    def test_returns_user_row_for_existing_user(self):
        self._insert_user(username="sebas", password_hash="hashed-pw")
        user = get_user("sebas")
        assert user["username"] == "sebas"
        assert user["password_hash"] == "hashed-pw"

# ---------------------------------------------------------------------------
# Test suite: Transaction update & delete operations
# ---------------------------------------------------------------------------
class TestUpdateTransaction:
    def test_updates_amount(self):
        insert_transactions([make_purchase(amount=100)])
        tx_id = get_transactions()[0]["id"]
        result = update_transaction(tx_id, {"amount": 250.0})
        assert result is True
        assert get_transactions()[0]["amount"] == 250.0

    def test_updates_merchant(self):
        insert_transactions([make_purchase(merchant="OXXO")])
        tx_id = get_transactions()[0]["id"]
        update_transaction(tx_id, {"merchant": "WALMART"})
        assert get_transactions()[0]["merchant"] == "WALMART"

    def test_updates_category_and_uppercases(self):
        insert_transactions([make_purchase()])
        tx_id = get_transactions()[0]["id"]
        update_transaction(tx_id, {"category": "food"})
        assert get_transactions()[0]["category"] == "FOOD"

    def test_ignores_non_updatable_fields(self):
        insert_transactions([make_purchase()])
        tx_id = get_transactions()[0]["id"]
        result = update_transaction(tx_id, {"id": 9999, "created_at": "2000-01-01T00:00:00"})
        assert result is False
        row = get_transactions()[0]
        assert row["id"] == tx_id
        assert row["created_at"] != "2000-01-01T00:00:00"

    def test_updates_bank_and_type(self):
        insert_transactions([make_purchase()])
        tx_id = get_transactions()[0]["id"]
        result = update_transaction(tx_id, {"bank": "bbva", "type": "transfer"})
        assert result is True
        row = get_transactions()[0]
        assert row["bank"] == "bbva"
        assert row["type"] == "transfer"

    def test_returns_false_for_nonexistent_id(self):
        result = update_transaction(9999, {"amount": 100.0})
        assert result is False

    def test_category_none_is_not_uppercased(self):
        insert_transactions([make_purchase()])
        tx_id = get_transactions()[0]["id"]
        update_transaction(tx_id, {"category": "food"})
        update_transaction(tx_id, {"category": None})
        assert get_transactions()[0]["category"] is None


class TestDeleteTransaction:
    def test_deletes_existing_transaction(self):
        insert_transactions([make_purchase()])
        tx_id = get_transactions()[0]["id"]
        result = delete_transaction(tx_id)
        assert result is True
        assert get_transactions() == []

    def test_returns_false_for_nonexistent_id(self):
        result = delete_transaction(9999)
        assert result is False

    def test_only_deletes_targeted_row(self):
        insert_transactions([make_purchase(amount=100), make_purchase(amount=200)])
        rows = get_transactions()
        delete_transaction(rows[0]["id"])
        remaining = get_transactions()
        assert len(remaining) == 1
        assert remaining[0]["amount"] == rows[1]["amount"]

# ---------------------------------------------------------------------------
# Test suite: Schema migrations (init_db run on an already-initialized DB)
# ---------------------------------------------------------------------------
class TestMigrations:
    def test_init_db_is_idempotent(self):
        init_db()
        init_db()
        cols = [r["name"] for r in get_connection().execute("PRAGMA table_info(categories)")]
        assert cols.count("kind") == 1
        assert cols.count("budget") == 1

    def test_kind_backfill_infers_income_and_expense(self):
        # Simulate a pre-existing DB from before `kind` existed: categorize
        # transactions, then recreate `categories` without the new columns.
        insert_transactions([make_transfer(), make_purchase(merchant="OXXO")])
        update_categories([
            {"id": get_transactions(tx_type="transfer")[0]["id"], "category": "salary"},
            {"id": get_transactions(tx_type="purchase")[0]["id"], "category": "food"},
        ])
        with _connection() as conn:
            conn.execute("ALTER TABLE categories RENAME TO categories_old")
            conn.execute("CREATE TABLE categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)")
            conn.execute("INSERT INTO categories (name) VALUES ('SALARY'), ('FOOD')")
            conn.execute("DROP TABLE categories_old")

        init_db()  # must detect the missing `kind` column, add it, and backfill

        cats = {c["name"]: c for c in get_categories(detailed=True)}
        assert cats["SALARY"]["kind"] == "income"
        assert cats["FOOD"]["kind"] == "expense"

    def test_ignored_transfers_seeded_from_constants(self):
        rules = get_ignored_transfers()
        assert any(r["account_last4"] == "6184" and r["bank"] == "Mercado Pago W" for r in rules)

    class _FakeMissingColumnConn:
        """Wraps a real connection, but reports a column as missing from
        PRAGMA table_info even though it already exists -- simulating a
        concurrent caller that lost the race between the PRAGMA check and
        the ALTER (backend/db/storage.py's _add_column_if_missing)."""

        def __init__(self, real_conn):
            self._real = real_conn

        def execute(self, sql, *args, **kwargs):
            if sql.strip().upper().startswith("PRAGMA TABLE_INFO"):
                return self._real.execute("SELECT NULL AS name WHERE 0")
            return self._real.execute(sql, *args, **kwargs)

    def test_add_column_tolerates_losing_race(self):
        conn = get_connection()
        fake = self._FakeMissingColumnConn(conn)
        # "kind" already exists on categories; the fake makes the PRAGMA
        # check miss it, so the ALTER below is the one that must fail
        # gracefully with "duplicate column name".
        result = storage._add_column_if_missing(fake, "categories", "kind", "TEXT")
        assert result is False
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(categories)")]
        assert cols.count("kind") == 1
        conn.close()

    def test_add_column_reraises_other_operational_errors(self):
        conn = get_connection()
        with pytest.raises(sqlite3.OperationalError):
            storage._add_column_if_missing(conn, "no_such_table", "x", "TEXT")
        conn.close()

    def test_init_db_dedupes_existing_ignored_transfer_duplicates(self):
        # Simulate a pre-existing DB from before the unique index existed:
        # drop it, then insert a duplicate the index would otherwise block.
        with _connection() as conn:
            conn.execute("DROP INDEX IF EXISTS idx_ignored_transfers_unique")
            conn.execute(
                "INSERT INTO ignored_transfers (account_last4, bank) VALUES (?, ?)",
                ("6184", "mercado pago w"),  # duplicate of a seeded rule, different case
            )
        assert len(get_ignored_transfers()) == len(storage.IGNORED_ACCOUNT_TRANSFERS) + 1

        init_db()

        rules = get_ignored_transfers()
        assert len(rules) == len(storage.IGNORED_ACCOUNT_TRANSFERS)
        index_row = get_connection().execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_ignored_transfers_unique'"
        ).fetchone()
        assert index_row is not None


# ---------------------------------------------------------------------------
# Test suite: Category detail, rename, merge & delete
# ---------------------------------------------------------------------------
class TestCategoryManagement:
    def test_detailed_listing_includes_kind_budget_and_count(self):
        create_category("FOOD", kind="expense")
        insert_transactions([make_purchase(merchant="OXXO")])
        update_categories([{"id": get_transactions()[0]["id"], "category": "food"}])
        cats = {c["name"]: c for c in get_categories(detailed=True)}
        assert cats["FOOD"]["kind"] == "expense"
        assert cats["FOOD"]["count"] == 1

    def test_rename_cascades_to_transactions(self):
        create_category("FOOD")
        cat_id = next(c["id"] for c in get_categories(detailed=True) if c["name"] == "FOOD")
        insert_transactions([make_purchase(merchant="OXXO")])
        update_categories([{"id": get_transactions()[0]["id"], "category": "food"}])

        update_category(cat_id, {"name": "groceries"})
        assert get_transactions()[0]["category"] == "GROCERIES"
        assert "GROCERIES" in get_categories()
        assert "FOOD" not in get_categories()

    def test_rename_onto_existing_category_merges(self):
        create_category("FOOD")
        create_category("GROCERIES")
        food_id = next(c["id"] for c in get_categories(detailed=True) if c["name"] == "FOOD")
        insert_transactions([make_purchase(merchant="OXXO")])
        update_categories([{"id": get_transactions()[0]["id"], "category": "food"}])

        update_category(food_id, {"name": "groceries"})
        assert get_transactions()[0]["category"] == "GROCERIES"
        assert get_categories() == ["GROCERIES"]

    def test_delete_nulls_transactions_category(self):
        create_category("FOOD")
        cat_id = next(c["id"] for c in get_categories(detailed=True) if c["name"] == "FOOD")
        insert_transactions([make_purchase(merchant="OXXO")])
        update_categories([{"id": get_transactions()[0]["id"], "category": "food"}])

        assert delete_category(cat_id) is True
        assert get_transactions()[0]["category"] is None
        assert "FOOD" not in get_categories()

    def test_delete_returns_false_for_missing_id(self):
        assert delete_category(9999) is False

    def test_update_returns_none_for_missing_id(self):
        assert update_category(9999, {"budget": 100}) is None

    def test_update_sets_budget(self):
        create_category("FOOD")
        cat_id = next(c["id"] for c in get_categories(detailed=True) if c["name"] == "FOOD")
        update_category(cat_id, {"budget": 2500.0})
        cats = {c["name"]: c for c in get_categories(detailed=True)}
        assert cats["FOOD"]["budget"] == 2500.0

    def test_merge_applies_kind_and_budget_to_target(self):
        create_category("FOOD")
        create_category("GROCERIES")
        food_id = next(c["id"] for c in get_categories(detailed=True) if c["name"] == "FOOD")
        groceries_id = next(c["id"] for c in get_categories(detailed=True) if c["name"] == "GROCERIES")

        result = update_category(food_id, {"name": "groceries", "kind": "expense", "budget": 1500.0})

        assert result["id"] == groceries_id
        assert result["name"] == "GROCERIES"
        assert result["kind"] == "expense"
        assert result["budget"] == 1500.0
        assert get_categories() == ["GROCERIES"]
        cats = {c["name"]: c for c in get_categories(detailed=True)}
        assert cats["GROCERIES"]["kind"] == "expense"
        assert cats["GROCERIES"]["budget"] == 1500.0

    def test_merge_without_kind_or_budget_keeps_target_values(self):
        create_category("FOOD")
        create_category("GROCERIES", kind="expense")
        food_id = next(c["id"] for c in get_categories(detailed=True) if c["name"] == "FOOD")
        groceries_id = next(c["id"] for c in get_categories(detailed=True) if c["name"] == "GROCERIES")
        update_category(groceries_id, {"budget": 2000.0})

        result = update_category(food_id, {"name": "groceries"})

        assert result["kind"] == "expense"
        assert result["budget"] == 2000.0

    def test_rename_with_kind_and_budget_updates_renamed_row(self):
        create_category("FOOD")
        cat_id = next(c["id"] for c in get_categories(detailed=True) if c["name"] == "FOOD")

        result = update_category(cat_id, {"name": "groceries", "kind": "expense", "budget": 900.0})

        assert result["id"] == cat_id
        assert result["name"] == "GROCERIES"
        assert result["kind"] == "expense"
        assert result["budget"] == 900.0

    def test_non_string_name_is_ignored(self):
        create_category("FOOD")
        cat_id = next(c["id"] for c in get_categories(detailed=True) if c["name"] == "FOOD")

        result = update_category(cat_id, {"name": 5, "budget": 10.0})

        assert result["name"] == "FOOD"
        assert result["budget"] == 10.0


# ---------------------------------------------------------------------------
# Test suite: Category suggestions for uncategorized transactions
# ---------------------------------------------------------------------------
class TestCategorySuggestions:
    def test_suggests_most_frequent_category_for_merchant(self):
        insert_transactions([
            make_purchase(merchant="OXXO", amount=50, date="2026-06-01T10:00:00"),
            make_purchase(merchant="OXXO", amount=60, date="2026-06-05T10:00:00"),
        ])
        ids = [tx["id"] for tx in get_transactions()]
        update_categories([
            {"id": ids[0], "category": "groceries"},
            {"id": ids[1], "category": "groceries"},
        ])
        insert_transactions([make_purchase(merchant="OXXO", amount=70, date="2026-06-10T10:00:00")])
        uncategorized = get_uncategorized()
        assert len(uncategorized) == 1
        assert uncategorized[0]["suggested_category"] == "GROCERIES"

    def test_no_suggestion_when_no_history(self):
        insert_transactions([make_purchase(merchant="NEW MERCHANT")])
        assert get_uncategorized()[0]["suggested_category"] is None


# ---------------------------------------------------------------------------
# Test suite: get_breakdown with year support
# ---------------------------------------------------------------------------
class TestBreakdownYear:
    def test_year_aggregates_across_months(self):
        insert_transactions([
            make_purchase(amount=100, date="2026-01-10T10:00:00", merchant="OXXO"),
            make_purchase(amount=200, date="2026-06-10T10:00:00", merchant="OXXO"),
        ])
        data = get_breakdown(year="2026")
        assert sum(r["total"] for r in data["expenses"]) == 300.0

    def test_month_still_works(self):
        insert_transactions([make_purchase(amount=100, date="2026-06-10T10:00:00", merchant="OXXO")])
        data = get_breakdown(month="2026-06")
        assert sum(r["total"] for r in data["expenses"]) == 100.0


# ---------------------------------------------------------------------------
# Test suite: Recurring expense detection
# ---------------------------------------------------------------------------
class TestRecurring:
    def test_detects_three_consecutive_months_within_tolerance(self):
        insert_transactions([
            make_purchase(merchant="NETFLIX", amount=199, date="2026-04-05T10:00:00"),
            make_purchase(merchant="NETFLIX", amount=199, date="2026-05-05T10:00:00"),
            make_purchase(merchant="NETFLIX", amount=210, date="2026-06-05T10:00:00"),
        ])
        results = get_recurring("2026-06")
        assert any(r["merchant"] == "NETFLIX" for r in results)

    def test_ignores_merchant_with_a_gap(self):
        insert_transactions([
            make_purchase(merchant="ONEOFF", amount=100, date="2026-01-05T10:00:00"),
            make_purchase(merchant="ONEOFF", amount=100, date="2026-06-05T10:00:00"),
        ])
        results = get_recurring("2026-06")
        assert not any(r["merchant"] == "ONEOFF" for r in results)

    def test_ignores_merchant_with_outlier_amount(self):
        insert_transactions([
            make_purchase(merchant="VARIABLE", amount=100, date="2026-04-05T10:00:00"),
            make_purchase(merchant="VARIABLE", amount=100, date="2026-05-05T10:00:00"),
            make_purchase(merchant="VARIABLE", amount=1000, date="2026-06-05T10:00:00"),
        ])
        results = get_recurring("2026-06")
        assert not any(r["merchant"] == "VARIABLE" for r in results)


# ---------------------------------------------------------------------------
# Test suite: Settings key/value store
# ---------------------------------------------------------------------------
class TestSettings:
    def test_returns_none_when_unset(self):
        assert get_setting("savings_goal") is None

    def test_set_and_get(self):
        set_setting("savings_goal", 5000)
        assert get_setting("savings_goal") == "5000"

    def test_set_none_clears(self):
        set_setting("savings_goal", 5000)
        set_setting("savings_goal", None)
        assert get_setting("savings_goal") is None


# ---------------------------------------------------------------------------
# Test suite: Ignored transfer rules & filtering on insert
# ---------------------------------------------------------------------------
class TestIgnoredTransfers:
    def test_seeded_rules_are_listed(self):
        rules = get_ignored_transfers()
        assert len(rules) == len(storage.IGNORED_ACCOUNT_TRANSFERS)

    def test_create_duplicate_rule_is_idempotent(self):
        baseline = len(get_ignored_transfers())
        first = create_ignored_transfer("1234", "TEST BANK")
        assert len(get_ignored_transfers()) == baseline + 1

        second = create_ignored_transfer("1234", "test bank")  # same rule, different case
        assert second["id"] == first["id"]
        assert len(get_ignored_transfers()) == baseline + 1

    def test_create_and_delete_rule(self):
        rule = create_ignored_transfer("1234", "TEST BANK")
        assert rule["account_last4"] == "1234"
        rules = get_ignored_transfers()
        assert any(r["id"] == rule["id"] for r in rules)

        assert delete_ignored_transfer(rule["id"]) is True
        rules = get_ignored_transfers()
        assert not any(r["id"] == rule["id"] for r in rules)

    def test_delete_returns_false_for_missing_id(self):
        assert delete_ignored_transfer(9999) is False

    def test_insert_skips_incoming_ignored_transfer(self):
        create_ignored_transfer("6184", "Mercado Pago W")
        tx = make_transfer()
        tx["source_account"] = "6184"
        tx["sender_bank"] = "Mercado Pago W"
        count = insert_transactions([tx])
        assert count == 0
        assert get_transactions() == []

    def test_insert_skips_outgoing_ignored_transfer(self):
        create_ignored_transfer("9066", "BBVA")
        tx = {
            "bank": "santander",
            "type": "outgoing_transfer",
            "amount": 500.0,
            "currency": "MXN",
            "date": "2026-06-01T10:00:00",
            "dest_account_last4": "9066",
            "dest_bank": "BBVA",
        }
        count = insert_transactions([tx])
        assert count == 0

    def test_insert_keeps_non_matching_transfer(self):
        create_ignored_transfer("6184", "Mercado Pago W")
        count = insert_transactions([make_transfer()])
        assert count == 1

    def test_is_ignored_transfer_case_insensitive_bank(self):
        create_ignored_transfer("6184", "Mercado Pago W")
        tx = make_transfer()
        tx["source_account"] = "6184"
        tx["sender_bank"] = "mercado pago w"
        assert is_ignored_transfer(tx) is True


# ---------------------------------------------------------------------------
# Test suite: Sync status
# ---------------------------------------------------------------------------
class TestStatus:
    def test_empty_db(self):
        status = get_status()
        assert status["last_synced"] is None
        assert status["uncategorized"] == 0

    def test_reports_uncategorized_count(self):
        insert_transactions([make_purchase(), make_purchase(amount=200)])
        assert get_status()["uncategorized"] == 2

    def test_excludes_manual_transactions_from_last_synced(self):
        tx = make_purchase()
        tx["reference"] = "MAN-1700000000-123"
        insert_transactions([tx])
        assert get_status()["last_synced"] is None

    def test_includes_ingested_transactions_in_last_synced(self):
        insert_transactions([make_purchase()])
        assert get_status()["last_synced"] is not None


# ---------------------------------------------------------------------------
# Test suite: Latest transaction date (ingestion cursor source)
# ---------------------------------------------------------------------------
class TestGetLatestTxDate:
    def test_returns_none_for_empty_db(self):
        assert get_latest_tx_date(["santander"]) is None

    def test_returns_max_date_for_single_bank(self):
        insert_transactions([
            make_purchase(date="2026-06-15T15:01:07"),
            make_purchase(date="2026-06-20T10:00:00"),
        ])
        assert get_latest_tx_date(["santander"]) == "2026-06-20T10:00:00"

    def test_returns_max_date_across_multiple_banks(self):
        insert_transactions([make_purchase(date="2026-06-10T08:00:00")])
        tx = make_purchase(date="2026-06-25T09:00:00")
        tx["bank"] = "santander likeu"
        insert_transactions([tx])
        assert get_latest_tx_date(["santander", "santander likeu"]) == "2026-06-25T09:00:00"

    def test_ignores_banks_not_in_list(self):
        tx = make_purchase(date="2026-06-25T09:00:00")
        tx["bank"] = "bbva"
        insert_transactions([tx])
        assert get_latest_tx_date(["santander"]) is None

    def test_excludes_manual_transactions(self):
        insert_transactions([make_purchase(date="2026-06-10T08:00:00")])
        manual = make_purchase(date="2026-06-30T12:00:00")
        manual["reference"] = "MAN-1700000000-123"
        insert_transactions([manual])
        assert get_latest_tx_date(["santander"]) == "2026-06-10T08:00:00"

    def test_includes_latest_tx_dates_in_status(self):
        from backend.constants import BANK_SANTANDER
        tx = make_purchase(date="2026-06-15T15:01:07")
        tx["bank"] = BANK_SANTANDER
        insert_transactions([tx])
        status = get_status()
        assert status["latest_tx_dates"]["santander"] == "2026-06-15T15:01:07"

    def test_latest_tx_dates_source_is_none_when_no_data(self):
        status = get_status()
        assert status["latest_tx_dates"]["santander"] is None
