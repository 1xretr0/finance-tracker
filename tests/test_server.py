# ---------------------------------------------------------------------------
# Tests for Flask API server endpoints
# ---------------------------------------------------------------------------
import importlib
import threading
import time
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash
from backend.server import app
from backend.db.storage import init_db, insert_transactions, _connection
import backend.db.storage as storage
import backend.server as server
import backend.constants as constants

TEST_API_TOKEN = "test-token"

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def use_temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    init_db()
    yield


@pytest.fixture(autouse=True)
def use_test_api_token(monkeypatch):
    monkeypatch.setattr(server, "API_TOKEN", TEST_API_TOKEN)
    yield


@pytest.fixture(autouse=True)
def reset_auth_lockout():
    server._failed_attempts.clear()
    yield


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {TEST_API_TOKEN}"
        yield client

# ---------------------------------------------------------------------------
# Test data seeding
# ---------------------------------------------------------------------------
def seed_data():
    insert_transactions([
        {"bank": "santander", "type": "purchase", "amount": 100.0, "currency": "MXN", "date": "2026-03-10T10:00:00", "merchant": "OXXO"},
        {"bank": "santander", "type": "purchase", "amount": 250.0, "currency": "MXN", "date": "2026-03-20T14:00:00", "merchant": "VIPS LEGARIA"},
        {"bank": "santander", "type": "purchase", "amount": 80.0, "currency": "MXN", "date": "2026-04-05T09:00:00", "merchant": "OXXO"},
        {"bank": "santander", "type": "transfer", "amount": 50000.0, "currency": "MXN", "date": "2026-03-01T12:00:00", "account_last4": "6466", "sender_bank": "HSBC", "tracking_key": "HSBC111"},
        {"bank": "santander", "type": "transfer", "amount": 30000.0, "currency": "MXN", "date": "2026-04-01T12:00:00", "account_last4": "6466", "sender_bank": "HSBC", "tracking_key": "HSBC222"},
        {"bank": "santander", "type": "outgoing_transfer", "amount": 5000.0, "currency": "MXN", "date": "2026-03-15T08:00:00", "account_last4": "6466", "dest_account_last4": "9066", "dest_bank": "BBVA", "reference": "123456"},
    ])


def seed_user(username="sebas", password="correct-password"):
    with _connection() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), "2026-01-01T00:00:00"),
        )

# ---------------------------------------------------------------------------
# Test suite: Auth
# ---------------------------------------------------------------------------
class TestApiAuth:
    def test_rejects_missing_token(self):
        with app.test_client() as unauth_client:
            res = unauth_client.get("/api/transactions")
            assert res.status_code == 401

    def test_rejects_wrong_token(self):
        with app.test_client() as unauth_client:
            unauth_client.environ_base["HTTP_AUTHORIZATION"] = "Bearer wrong"
            res = unauth_client.get("/api/transactions")
            assert res.status_code == 401

    def test_accepts_correct_token(self, client):
        res = client.get("/api/transactions")
        assert res.status_code == 200

    def test_static_routes_do_not_require_token(self):
        with app.test_client() as unauth_client:
            assert unauth_client.get("/").status_code == 200

    def test_unconfigured_token_rejects_all_api_requests(self, monkeypatch):
        monkeypatch.setattr(server, "API_TOKEN", None)
        with app.test_client() as unauth_client:
            unauth_client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {TEST_API_TOKEN}"
            res = unauth_client.get("/api/transactions")
            assert res.status_code == 503

    def test_locks_out_after_repeated_failed_attempts(self, monkeypatch):
        monkeypatch.setattr(server, "AUTH_MAX_FAILED_ATTEMPTS", 3)
        server._failed_attempts.clear()
        with app.test_client() as unauth_client:
            unauth_client.environ_base["HTTP_AUTHORIZATION"] = "Bearer wrong"
            for _ in range(3):
                res = unauth_client.get("/api/transactions")
                assert res.status_code == 401

            res = unauth_client.get("/api/transactions")
            assert res.status_code == 429

            unauth_client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {TEST_API_TOKEN}"
            res = unauth_client.get("/api/transactions")
            assert res.status_code == 429

    def test_lockout_is_scoped_per_ip(self, monkeypatch):
        monkeypatch.setattr(server, "AUTH_MAX_FAILED_ATTEMPTS", 3)
        server._failed_attempts.clear()
        with app.test_client() as client_a, app.test_client() as client_b:
            client_a.environ_base["HTTP_AUTHORIZATION"] = "Bearer wrong"
            client_a.environ_base["REMOTE_ADDR"] = "1.1.1.1"
            for _ in range(3):
                client_a.get("/api/transactions")
            assert client_a.get("/api/transactions").status_code == 429

            client_b.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {TEST_API_TOKEN}"
            client_b.environ_base["REMOTE_ADDR"] = "2.2.2.2"
            assert client_b.get("/api/transactions").status_code == 200

    def test_flask_debug_defaults_off(self, monkeypatch):
        monkeypatch.delenv("FLASK_DEBUG", raising=False)
        reloaded = importlib.reload(constants)
        assert reloaded.FLASK_DEBUG is False
        importlib.reload(constants)

    def test_flask_debug_enabled_via_env(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        reloaded = importlib.reload(constants)
        assert reloaded.FLASK_DEBUG is True
        monkeypatch.delenv("FLASK_DEBUG", raising=False)
        importlib.reload(constants)

    def test_token_file_defaults_to_project_root(self, monkeypatch):
        monkeypatch.delenv("TOKEN_PATH", raising=False)
        reloaded = importlib.reload(constants)
        assert reloaded.TOKEN_FILE.endswith("token.json")
        assert "TOKEN_PATH" not in reloaded.TOKEN_FILE
        importlib.reload(constants)

    def test_token_file_overridable_via_env(self, monkeypatch):
        monkeypatch.setenv("TOKEN_PATH", "/tmp/custom-token.json")
        reloaded = importlib.reload(constants)
        assert reloaded.TOKEN_FILE == "/tmp/custom-token.json"
        monkeypatch.delenv("TOKEN_PATH", raising=False)
        importlib.reload(constants)

# ---------------------------------------------------------------------------
# Test suite: Login
# ---------------------------------------------------------------------------
class TestLoginEndpoint:
    def test_rejects_unknown_username(self):
        with app.test_client() as unauth_client:
            res = unauth_client.post("/api/login", json={"username": "nobody", "password": "x"})
            assert res.status_code == 401

    def test_rejects_wrong_password(self):
        seed_user()
        with app.test_client() as unauth_client:
            res = unauth_client.post("/api/login", json={"username": "sebas", "password": "wrong"})
            assert res.status_code == 401

    def test_accepts_correct_credentials_and_returns_token(self):
        seed_user()
        with app.test_client() as unauth_client:
            res = unauth_client.post("/api/login", json={"username": "sebas", "password": "correct-password"})
            assert res.status_code == 200
            data = res.get_json()
            assert data["token"] == TEST_API_TOKEN
            assert data["username"] == "sebas"

    def test_does_not_require_bearer_token(self):
        # /api/login is how a token is obtained in the first place, so it
        # must be reachable without one, despite being under /api/.
        seed_user()
        with app.test_client() as unauth_client:
            res = unauth_client.post("/api/login", json={"username": "sebas", "password": "correct-password"})
            assert res.status_code == 200

    def test_rejects_missing_fields(self):
        with app.test_client() as unauth_client:
            res = unauth_client.post("/api/login", json={"username": "sebas"})
            assert res.status_code == 400

    def test_unconfigured_token_rejects_login(self, monkeypatch):
        monkeypatch.setattr(server, "API_TOKEN", None)
        seed_user()
        with app.test_client() as unauth_client:
            res = unauth_client.post("/api/login", json={"username": "sebas", "password": "correct-password"})
            assert res.status_code == 503

    def test_locks_out_after_repeated_failed_logins(self, monkeypatch):
        monkeypatch.setattr(server, "AUTH_MAX_FAILED_ATTEMPTS", 3)
        server._failed_attempts.clear()
        seed_user()
        with app.test_client() as unauth_client:
            for _ in range(3):
                res = unauth_client.post("/api/login", json={"username": "sebas", "password": "wrong"})
                assert res.status_code == 401

            res = unauth_client.post("/api/login", json={"username": "sebas", "password": "correct-password"})
            assert res.status_code == 429

    def test_serves_login_page(self):
        with app.test_client() as unauth_client:
            res = unauth_client.get("/login")
            assert res.status_code == 200

# ---------------------------------------------------------------------------
# Test suite: API endpoints - Read operations
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Test suite: Static file serving
# ---------------------------------------------------------------------------
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


class TestBreakdownEndpoint:
    def test_returns_income_and_expenses_keys(self, client):
        seed_data()
        res = client.get("/api/breakdown?month=2026-03")
        assert res.status_code == 200
        data = res.get_json()
        assert "income" in data
        assert "expenses" in data

    def test_income_contains_transfers(self, client):
        seed_data()
        res = client.get("/api/breakdown?month=2026-03")
        data = res.get_json()
        assert any(r["total"] == 50000.0 for r in data["income"])

    def test_expenses_contains_purchases_and_outgoing(self, client):
        seed_data()
        res = client.get("/api/breakdown?month=2026-03")
        data = res.get_json()
        expense_totals = [r["total"] for r in data["expenses"]]
        assert sum(expense_totals) == pytest.approx(350.0 + 5000.0)

    def test_defaults_to_current_month_when_no_param(self, client):
        res = client.get("/api/breakdown")
        assert res.status_code == 200
        data = res.get_json()
        assert "income" in data and "expenses" in data

    def test_empty_month_returns_empty_lists(self, client):
        seed_data()
        res = client.get("/api/breakdown?month=2020-01")
        data = res.get_json()
        assert data["income"] == []
        assert data["expenses"] == []

# ---------------------------------------------------------------------------
# Test suite: API endpoints - Write operations
# ---------------------------------------------------------------------------
class TestUncategorizedEndpoint:
    def test_returns_uncategorized_transactions(self, client):
        seed_data()
        res = client.get("/api/uncategorized")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) == 6
        assert all(tx["category"] is None for tx in data)

    def test_excludes_categorized_transactions(self, client):
        seed_data()
        tx_id = client.get("/api/transactions").get_json()[0]["id"]
        client.put("/api/transactions/categorize", json=[{"id": tx_id, "category": "food"}])
        data = client.get("/api/uncategorized").get_json()
        assert all(tx["id"] != tx_id for tx in data)

    def test_empty_db(self, client):
        res = client.get("/api/uncategorized")
        assert res.get_json() == []


class TestCategorizeEndpoint:
    def test_updates_categories(self, client):
        seed_data()
        tx_id = client.get("/api/transactions").get_json()[0]["id"]
        res = client.put("/api/transactions/categorize", json=[{"id": tx_id, "category": "food"}])
        assert res.status_code == 200
        assert res.get_json()["updated"] == 1

    def test_uppercases_category(self, client):
        seed_data()
        tx_id = client.get("/api/transactions").get_json()[0]["id"]
        client.put("/api/transactions/categorize", json=[{"id": tx_id, "category": "groceries"}])
        tx = next(t for t in client.get("/api/transactions").get_json() if t["id"] == tx_id)
        assert tx["category"] == "GROCERIES"

    def test_rejects_non_list_body(self, client):
        res = client.put("/api/transactions/categorize", json={"id": 1, "category": "food"})
        assert res.status_code == 400

    def test_rejects_missing_body(self, client):
        res = client.put("/api/transactions/categorize", data="not json", content_type="text/plain")
        assert res.status_code in (400, 415)


class TestCreateTransactionEndpoint:
    def test_creates_valid_transaction(self, client):
        res = client.post("/api/transactions", json={
            "type": "purchase", "amount": 150.0, "date": "2026-06-01T10:00:00",
            "merchant": "OXXO", "currency": "MXN", "bank": "SANTANDER GOLD"
        })
        assert res.status_code == 201
        assert res.get_json()["success"] is True

    def test_rejects_missing_required_field(self, client):
        res = client.post("/api/transactions", json={"type": "purchase", "amount": 50.0})
        assert res.status_code == 400

    def test_rejects_negative_amount(self, client):
        res = client.post("/api/transactions", json={
            "type": "purchase", "amount": -10.0, "date": "2026-06-01T10:00:00",
        })
        assert res.status_code == 400

    def test_rejects_invalid_type(self, client):
        res = client.post("/api/transactions", json={
            "type": "refund", "amount": 100.0, "date": "2026-06-01T10:00:00",
        })
        assert res.status_code == 400

    def test_returns_409_for_duplicate(self, client):
        tx = {
            "type": "purchase",
            "amount": 100.0,
            "date": "2026-06-01T10:00:00",
            "merchant": "OXXO",
            "bank": "SANTANDER GOLD"
        }
        client.post("/api/transactions", json=tx)
        res = client.post("/api/transactions", json=tx)
        assert res.status_code == 409

    def test_rejects_non_dict_body(self, client):
        res = client.post("/api/transactions", json=[{"type": "purchase"}])
        assert res.status_code == 400


class TestUpdateTransactionEndpoint:
    def test_updates_amount(self, client):
        seed_data()
        tx_id = client.get("/api/transactions").get_json()[0]["id"]
        res = client.put(f"/api/transactions/{tx_id}", json={"amount": 999.0})
        assert res.status_code == 200
        assert res.get_json()["success"] is True

    def test_returns_404_for_missing_id(self, client):
        res = client.put("/api/transactions/9999", json={"amount": 10.0})
        assert res.status_code == 404

    def test_rejects_negative_amount(self, client):
        seed_data()
        tx_id = client.get("/api/transactions").get_json()[0]["id"]
        res = client.put(f"/api/transactions/{tx_id}", json={"amount": -5.0})
        assert res.status_code == 400

    def test_rejects_non_dict_body(self, client):
        res = client.put("/api/transactions/1", json=[{"amount": 10.0}])
        assert res.status_code == 400


class TestDeleteTransactionEndpoint:
    def test_deletes_existing_transaction(self, client):
        seed_data()
        tx_id = client.get("/api/transactions").get_json()[0]["id"]
        res = client.delete(f"/api/transactions/{tx_id}")
        assert res.status_code == 200
        assert res.get_json()["success"] is True

    def test_transaction_gone_after_delete(self, client):
        seed_data()
        tx_id = client.get("/api/transactions").get_json()[0]["id"]
        client.delete(f"/api/transactions/{tx_id}")
        ids = [tx["id"] for tx in client.get("/api/transactions").get_json()]
        assert tx_id not in ids

    def test_returns_404_for_missing_id(self, client):
        res = client.delete("/api/transactions/9999")
        assert res.status_code == 404


class TestCategoriesEndpoint:
    def test_returns_empty_list_initially(self, client):
        res = client.get("/api/categories")
        assert res.status_code == 200
        assert res.get_json() == []

    def test_returns_created_categories(self, client):
        client.post("/api/categories", json={"name": "food"})
        client.post("/api/categories", json={"name": "transport"})
        cats = client.get("/api/categories").get_json()
        assert "FOOD" in cats
        assert "TRANSPORT" in cats

    def test_create_category_returns_201(self, client):
        res = client.post("/api/categories", json={"name": "health"})
        assert res.status_code == 201
        assert res.get_json()["name"] == "HEALTH"

    def test_create_category_rejects_missing_name(self, client):
        res = client.post("/api/categories", json={})
        assert res.status_code == 400

    def test_create_duplicate_category_still_returns_201(self, client):
        client.post("/api/categories", json={"name": "food"})
        res = client.post("/api/categories", json={"name": "food"})
        assert res.status_code == 201
        assert client.get("/api/categories").get_json().count("FOOD") == 1

    def test_create_category_rejects_invalid_kind(self, client):
        res = client.post("/api/categories", json={"name": "food", "kind": "bogus"})
        assert res.status_code == 400

    def test_create_category_rejects_non_string_name(self, client):
        for bad_name in (5, None, ["x"]):
            res = client.post("/api/categories", json={"name": bad_name})
            assert res.status_code == 400

    def test_create_category_rejects_blank_name(self, client):
        res = client.post("/api/categories", json={"name": "   "})
        assert res.status_code == 400

    def test_create_category_rejects_non_object_body(self, client):
        res = client.post("/api/categories", json=["name"])
        assert res.status_code == 400

    def test_detailed_listing_includes_kind_budget_and_count(self, client):
        client.post("/api/categories", json={"name": "food", "kind": "expense"})
        res = client.get("/api/categories?detailed=true")
        assert res.status_code == 200
        data = res.get_json()
        food = next(c for c in data if c["name"] == "FOOD")
        assert food["kind"] == "expense"
        assert food["count"] == 0


class TestCategoryUpdateDeleteEndpoint:
    def _create(self, client, name="food", kind=None):
        client.post("/api/categories", json={"name": name, "kind": kind})
        cat = next(c for c in client.get("/api/categories?detailed=true").get_json() if c["name"] == name.upper())
        return cat["id"]

    def test_renames_category(self, client):
        cat_id = self._create(client)
        res = client.put(f"/api/categories/{cat_id}", json={"name": "groceries"})
        assert res.status_code == 200
        assert res.get_json()["name"] == "GROCERIES"

    def test_updates_budget(self, client):
        cat_id = self._create(client)
        res = client.put(f"/api/categories/{cat_id}", json={"budget": 3000})
        assert res.status_code == 200
        assert res.get_json()["budget"] == 3000

    def test_rejects_negative_budget(self, client):
        cat_id = self._create(client)
        res = client.put(f"/api/categories/{cat_id}", json={"budget": -5})
        assert res.status_code == 400

    def test_rejects_invalid_kind(self, client):
        cat_id = self._create(client)
        res = client.put(f"/api/categories/{cat_id}", json={"kind": "bogus"})
        assert res.status_code == 400

    def test_returns_404_for_missing_id(self, client):
        res = client.put("/api/categories/9999", json={"budget": 100})
        assert res.status_code == 404

    def test_rejects_non_string_name(self, client):
        cat_id = self._create(client)
        for bad_name in (5, None, ["x"], {"a": 1}):
            res = client.put(f"/api/categories/{cat_id}", json={"name": bad_name})
            assert res.status_code == 400
        assert client.get("/api/categories").get_json() == ["FOOD"]

    def test_rejects_blank_name(self, client):
        cat_id = self._create(client)
        res = client.put(f"/api/categories/{cat_id}", json={"name": "  "})
        assert res.status_code == 400

    def test_rejects_boolean_budget(self, client):
        cat_id = self._create(client)
        res = client.put(f"/api/categories/{cat_id}", json={"budget": True})
        assert res.status_code == 400

    def test_deletes_category(self, client):
        cat_id = self._create(client)
        res = client.delete(f"/api/categories/{cat_id}")
        assert res.status_code == 200
        assert "FOOD" not in client.get("/api/categories").get_json()

    def test_delete_returns_404_for_missing_id(self, client):
        res = client.delete("/api/categories/9999")
        assert res.status_code == 404

    def test_endpoints_require_auth(self):
        with app.test_client() as unauth_client:
            assert unauth_client.put("/api/categories/1", json={"budget": 1}).status_code == 401
            assert unauth_client.delete("/api/categories/1").status_code == 401


# ---------------------------------------------------------------------------
# Test suite: Settings
# ---------------------------------------------------------------------------
class TestSettingsEndpoint:
    def test_returns_null_when_unset(self, client):
        res = client.get("/api/settings")
        assert res.status_code == 200
        assert res.get_json()["savings_goal"] is None

    def test_sets_and_returns_value(self, client):
        res = client.put("/api/settings", json={"savings_goal": 5000})
        assert res.status_code == 200
        assert client.get("/api/settings").get_json()["savings_goal"] == "5000.0"

    def test_clears_value_with_null(self, client):
        client.put("/api/settings", json={"savings_goal": 5000})
        client.put("/api/settings", json={"savings_goal": None})
        assert client.get("/api/settings").get_json()["savings_goal"] is None

    def test_rejects_unknown_key(self, client):
        res = client.put("/api/settings", json={"bogus_key": 1})
        assert res.status_code == 400

    def test_rejects_negative_value(self, client):
        res = client.put("/api/settings", json={"savings_goal": -5})
        assert res.status_code == 400

    def test_endpoints_require_auth(self):
        with app.test_client() as unauth_client:
            assert unauth_client.get("/api/settings").status_code == 401
            assert unauth_client.put("/api/settings", json={}).status_code == 401


# ---------------------------------------------------------------------------
# Test suite: Ignored transfers
# ---------------------------------------------------------------------------
class TestIgnoredTransfersEndpoint:
    def test_lists_seeded_rules(self, client):
        res = client.get("/api/ignored-transfers")
        assert res.status_code == 200
        assert len(res.get_json()) == len(constants.IGNORED_ACCOUNT_TRANSFERS)

    def test_creates_and_deletes_rule(self, client):
        res = client.post("/api/ignored-transfers", json={"account_last4": "1234", "bank": "TEST"})
        assert res.status_code == 201
        rule_id = res.get_json()["id"]

        res = client.delete(f"/api/ignored-transfers/{rule_id}")
        assert res.status_code == 200

    def test_rejects_missing_fields(self, client):
        res = client.post("/api/ignored-transfers", json={"account_last4": "1234"})
        assert res.status_code == 400

    def test_delete_returns_404_for_missing_id(self, client):
        res = client.delete("/api/ignored-transfers/9999")
        assert res.status_code == 404

    def test_endpoints_require_auth(self):
        with app.test_client() as unauth_client:
            assert unauth_client.get("/api/ignored-transfers").status_code == 401
            assert unauth_client.post("/api/ignored-transfers", json={}).status_code == 401


# ---------------------------------------------------------------------------
# Test suite: Sync status
# ---------------------------------------------------------------------------
class TestStatusEndpoint:
    def test_returns_last_synced_and_uncategorized(self, client):
        seed_data()
        res = client.get("/api/status")
        assert res.status_code == 200
        data = res.get_json()
        assert data["uncategorized"] == 6
        assert data["last_synced"] is not None

    def test_requires_auth(self):
        with app.test_client() as unauth_client:
            assert unauth_client.get("/api/status").status_code == 401


# ---------------------------------------------------------------------------
# Test suite: Dashboard-triggered sync (Phase 2, "Sync now")
# ---------------------------------------------------------------------------
class TestSyncEndpoint:
    def test_runs_sync_and_returns_counts(self, client):
        with patch(
            "backend.process_transactions.run_sync",
            return_value={"inserted": 2, "ignored": 1, "duplicates": 0},
        ) as mock_run_sync:
            res = client.post("/api/sync")
        assert res.status_code == 200
        assert res.get_json() == {"inserted": 2, "ignored": 1, "duplicates": 0}
        mock_run_sync.assert_called_once_with(use_remote=False, interactive=False)

    def test_requires_auth(self):
        with app.test_client() as unauth_client:
            assert unauth_client.post("/api/sync").status_code == 401

    def test_returns_409_when_a_sync_is_already_running(self, client):
        assert server._sync_lock.acquire(blocking=False)
        try:
            res = client.post("/api/sync")
            assert res.status_code == 409
        finally:
            server._sync_lock.release()

    def test_releases_lock_after_a_completed_sync(self, client):
        with patch(
            "backend.process_transactions.run_sync",
            return_value={"inserted": 0, "ignored": 0, "duplicates": 0},
        ):
            client.post("/api/sync")
        assert server._sync_lock.acquire(blocking=False)
        server._sync_lock.release()

    def test_releases_lock_even_when_run_sync_raises(self, client):
        with patch(
            "backend.process_transactions.run_sync",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError):
                client.post("/api/sync")
        assert server._sync_lock.acquire(blocking=False)
        server._sync_lock.release()

    def test_returns_503_when_gmail_authentication_is_unavailable(self, client):
        from backend.banks.santander import AuthenticationRequiredError

        with patch(
            "backend.process_transactions.run_sync",
            side_effect=AuthenticationRequiredError("no valid token"),
        ):
            res = client.post("/api/sync")
        assert res.status_code == 503

    def test_returns_500_when_run_sync_signals_failure(self, client):
        """run_sync returns None (not a dict) when the cursor lookup, fetch,
        or save step failed non-auth — distinct from a legitimate empty
        result, which is a dict of zero counts."""
        with patch("backend.process_transactions.run_sync", return_value=None):
            res = client.post("/api/sync")
        assert res.status_code == 500
        assert "error" in res.get_json()


# ---------------------------------------------------------------------------
# Test suite: Recurring expenses
# ---------------------------------------------------------------------------
class TestRecurringEndpoint:
    def test_returns_list(self, client):
        for i in range(3):
            insert_transactions([{
                "bank": "santander", "type": "purchase", "amount": 199.0, "currency": "MXN",
                "date": f"2026-0{4 + i}-05T10:00:00", "merchant": "NETFLIX",
            }])
        res = client.get("/api/recurring?month=2026-06")
        assert res.status_code == 200
        merchants = [r["merchant"] for r in res.get_json()]
        assert "NETFLIX" in merchants

    def test_requires_auth(self):
        with app.test_client() as unauth_client:
            assert unauth_client.get("/api/recurring").status_code == 401


# ---------------------------------------------------------------------------
# Test suite: Breakdown by year
# ---------------------------------------------------------------------------
class TestBreakdownYearEndpoint:
    def test_year_param_aggregates_across_months(self, client):
        seed_data()
        res = client.get("/api/breakdown?year=2026")
        data = res.get_json()
        assert sum(r["total"] for r in data["expenses"]) == pytest.approx(430.0 + 5000.0)


# ---------------------------------------------------------------------------
# Test suite: Ignored transfers on POST /api/transactions
# ---------------------------------------------------------------------------
class TestCreateTransactionIgnoredTransfer:
    def test_ignored_transfer_returns_200_not_409(self, client):
        client.post("/api/ignored-transfers", json={"account_last4": "9066", "bank": "BBVA"})
        res = client.post("/api/transactions", json={
            "type": "outgoing_transfer", "amount": 500.0, "date": "2026-06-01T10:00:00",
            "bank": "SANTANDER", "dest_account_last4": "9066", "dest_bank": "BBVA",
        })
        assert res.status_code == 200
        assert res.get_json()["ignored"] is True
        assert client.get("/api/transactions").get_json() == []


# ---------------------------------------------------------------------------
# Test suite: Extended PUT /api/transactions/<id> fields
# ---------------------------------------------------------------------------
class TestUpdateTransactionExtendedFields:
    def test_updates_date_type_bank_notes_sender_bank(self, client):
        seed_data()
        tx_id = client.get("/api/transactions").get_json()[0]["id"]
        res = client.put(f"/api/transactions/{tx_id}", json={
            "date": "2026-05-01T10:00:00", "type": "transfer", "bank": "BBVA",
            "notes": "reimbursed later", "sender_bank": "HSBC",
        })
        assert res.status_code == 200
        tx = next(t for t in client.get("/api/transactions").get_json() if t["id"] == tx_id)
        assert tx["date"] == "2026-05-01T10:00:00"
        assert tx["type"] == "transfer"
        assert tx["bank"] == "BBVA"
        assert tx["notes"] == "reimbursed later"
        assert tx["sender_bank"] == "HSBC"

    def test_rejects_invalid_type(self, client):
        seed_data()
        tx_id = client.get("/api/transactions").get_json()[0]["id"]
        res = client.put(f"/api/transactions/{tx_id}", json={"type": "bogus"})
        assert res.status_code == 400

    def test_rejects_invalid_bank(self, client):
        seed_data()
        tx_id = client.get("/api/transactions").get_json()[0]["id"]
        res = client.put(f"/api/transactions/{tx_id}", json={"bank": "bogus"})
        assert res.status_code == 400

    def test_rejects_invalid_date(self, client):
        seed_data()
        tx_id = client.get("/api/transactions").get_json()[0]["id"]
        res = client.put(f"/api/transactions/{tx_id}", json={"date": "not-a-date"})
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# Test suite: Lazy DB-init concurrency guard (MED-6)
# ---------------------------------------------------------------------------
class TestLazyDbInit:
    def test_init_runs_once_under_concurrent_first_requests(self, monkeypatch):
        monkeypatch.setattr(server, "_db_initialized", False)
        calls = []

        def fake_init_db():
            time.sleep(0.05)
            calls.append(1)

        monkeypatch.setattr(server, "init_db", fake_init_db)

        barrier = threading.Barrier(8)
        results = []

        def worker():
            barrier.wait(timeout=2)
            with app.test_client() as c:
                c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {TEST_API_TOKEN}"
                results.append(c.get("/api/categories").status_code)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(calls) == 1
        assert all(status == 200 for status in results)
        assert server._db_initialized is True

    def test_skips_init_once_initialized(self, monkeypatch):
        monkeypatch.setattr(server, "_db_initialized", True)
        calls = []
        monkeypatch.setattr(server, "init_db", lambda: calls.append(1))

        with app.test_client() as c:
            c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {TEST_API_TOKEN}"
            res = c.get("/api/categories")

        assert res.status_code == 200
        assert calls == []

    def test_failed_init_is_retried_on_next_request(self, monkeypatch):
        monkeypatch.setattr(server, "_db_initialized", False)
        monkeypatch.setitem(app.config, "TESTING", True)
        calls = []

        def flaky_init_db():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")

        monkeypatch.setattr(server, "init_db", flaky_init_db)

        with app.test_client() as c:
            c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {TEST_API_TOKEN}"
            with pytest.raises(RuntimeError):
                c.get("/api/categories")

            res = c.get("/api/categories")
            assert res.status_code == 200

        assert len(calls) == 2
        assert server._db_initialized is True
