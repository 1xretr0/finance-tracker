import pytest
from backend.db.storage import init_db, insert_transactions, get_transactions, get_summary, get_connection
import backend.db.storage as storage


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    init_db()
    yield db_path


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

    def test_stores_all_fields(self):
        tx = make_transfer()
        insert_transactions([tx])
        rows = get_transactions()
        assert len(rows) == 1
        row = rows[0]
        assert row["sender_bank"] == "HSBC"
        assert row["tracking_key"] == "HSBC628982"
        assert row["concept"] == "NOMINA"


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
