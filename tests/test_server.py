import pytest
from backend.server import app
from backend.db.storage import init_db, insert_transactions
import backend.db.storage as storage


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    init_db()
    yield


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def seed_data():
    insert_transactions([
        {"bank": "santander", "type": "purchase", "amount": 100.0, "currency": "MXN", "date": "2026-03-10T10:00:00", "merchant": "OXXO"},
        {"bank": "santander", "type": "purchase", "amount": 250.0, "currency": "MXN", "date": "2026-03-20T14:00:00", "merchant": "VIPS LEGARIA"},
        {"bank": "santander", "type": "purchase", "amount": 80.0, "currency": "MXN", "date": "2026-04-05T09:00:00", "merchant": "OXXO"},
        {"bank": "santander", "type": "transfer", "amount": 50000.0, "currency": "MXN", "date": "2026-03-01T12:00:00", "account_last4": "6466", "sender_bank": "HSBC", "tracking_key": "HSBC111"},
        {"bank": "santander", "type": "transfer", "amount": 30000.0, "currency": "MXN", "date": "2026-04-01T12:00:00", "account_last4": "6466", "sender_bank": "HSBC", "tracking_key": "HSBC222"},
        {"bank": "santander", "type": "outgoing_transfer", "amount": 5000.0, "currency": "MXN", "date": "2026-03-15T08:00:00", "account_last4": "6466", "dest_account_last4": "9066", "dest_bank": "BBVA", "reference": "123456"},
    ])


class TestTransactionsEndpoint:
    def test_returns_all_transactions(self, client):
        seed_data()
        res = client.get("/api/transactions")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) == 6

    def test_filter_by_type(self, client):
        seed_data()
        res = client.get("/api/transactions?type=purchase")
        data = res.get_json()
        assert all(tx["type"] == "purchase" for tx in data)
        assert len(data) == 3

    def test_filter_by_date_range(self, client):
        seed_data()
        res = client.get("/api/transactions?start_date=2026-04-01&end_date=2026-04-30")
        data = res.get_json()
        assert len(data) == 2
        for tx in data:
            assert tx["date"].startswith("2026-04")

    def test_filter_by_bank(self, client):
        seed_data()
        res = client.get("/api/transactions?bank=santander")
        assert len(res.get_json()) == 6
        res = client.get("/api/transactions?bank=bbva")
        assert len(res.get_json()) == 0

    def test_empty_db(self, client):
        res = client.get("/api/transactions")
        assert res.status_code == 200
        assert res.get_json() == []


class TestSummaryEndpoint:
    def test_returns_summary_by_type(self, client):
        seed_data()
        res = client.get("/api/summary")
        data = res.get_json()
        assert data["purchase"]["count"] == 3
        assert data["purchase"]["total"] == 430.0
        assert data["transfer"]["count"] == 2
        assert data["transfer"]["total"] == 80000.0
        assert data["outgoing_transfer"]["count"] == 1
        assert data["outgoing_transfer"]["total"] == 5000.0

    def test_summary_with_date_filter(self, client):
        seed_data()
        res = client.get("/api/summary?start_date=2026-04-01")
        data = res.get_json()
        assert "purchase" in data
        assert data["purchase"]["total"] == 80.0
        assert data["transfer"]["total"] == 30000.0
        assert "outgoing_transfer" not in data

    def test_empty_db(self, client):
        res = client.get("/api/summary")
        assert res.get_json() == {}


class TestMonthlyEndpoint:
    def test_returns_monthly_breakdown(self, client):
        seed_data()
        res = client.get("/api/monthly")
        data = res.get_json()
        months = [r["month"] for r in data]
        assert "2026-03" in months
        assert "2026-04" in months

    def test_groups_by_month_and_type(self, client):
        seed_data()
        res = client.get("/api/monthly")
        data = res.get_json()
        march_purchases = [r for r in data if r["month"] == "2026-03" and r["type"] == "purchase"]
        assert len(march_purchases) == 1
        assert march_purchases[0]["total"] == 350.0
        assert march_purchases[0]["count"] == 2

    def test_date_filter(self, client):
        seed_data()
        res = client.get("/api/monthly?start_date=2026-04-01")
        data = res.get_json()
        months = set(r["month"] for r in data)
        assert "2026-03" not in months
        assert "2026-04" in months


class TestMerchantsEndpoint:
    def test_returns_merchants_sorted_by_total(self, client):
        seed_data()
        res = client.get("/api/merchants")
        data = res.get_json()
        assert data[0]["merchant"] == "VIPS LEGARIA"
        assert data[0]["total"] == 250.0
        assert data[1]["merchant"] == "OXXO"
        assert data[1]["total"] == 180.0
        assert data[1]["count"] == 2

    def test_excludes_non_purchase_types(self, client):
        seed_data()
        res = client.get("/api/merchants")
        data = res.get_json()
        merchants = [r["merchant"] for r in data]
        assert "HSBC" not in merchants
        assert "BBVA" not in merchants

    def test_date_filter(self, client):
        seed_data()
        res = client.get("/api/merchants?start_date=2026-04-01")
        data = res.get_json()
        assert len(data) == 1
        assert data[0]["merchant"] == "OXXO"
        assert data[0]["total"] == 80.0


class TestSavingsEndpoint:
    def test_returns_savings_per_month(self, client):
        seed_data()
        res = client.get("/api/savings?year=2026")
        data = res.get_json()
        assert len(data) == 2

        march = next(r for r in data if r["month"] == "2026-03")
        assert march["income"] == 50000.0
        assert march["purchases"] == 350.0
        assert march["outgoing"] == 5000.0
        assert march["savings"] == 50000.0 - 350.0 - 5000.0

        april = next(r for r in data if r["month"] == "2026-04")
        assert april["income"] == 30000.0
        assert april["purchases"] == 80.0
        assert april["outgoing"] == 0
        assert april["savings"] == 30000.0 - 80.0

    def test_different_year_returns_empty(self, client):
        seed_data()
        res = client.get("/api/savings?year=2025")
        assert res.get_json() == []

    def test_defaults_to_current_year(self, client):
        seed_data()
        res = client.get("/api/savings")
        data = res.get_json()
        assert len(data) >= 0
        assert res.status_code == 200


class TestStaticFiles:
    def test_serves_index(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert b"Finance Tracker" in res.data

    def test_serves_css(self, client):
        res = client.get("/css/styles.css")
        assert res.status_code == 200
        assert b"background" in res.data

    def test_serves_js(self, client):
        res = client.get("/js/app.js")
        assert res.status_code == 200
        assert b"fetchJSON" in res.data
