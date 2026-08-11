# ---------------------------------------------------------------------------
# Tests for the remote-push transaction sink
# ---------------------------------------------------------------------------
from unittest.mock import patch, MagicMock

import pytest
import requests

import backend.process_transactions as process_transactions
from backend.process_transactions import push_transactions

TEST_REMOTE_URL = "https://example.pythonanywhere.com"
TEST_TOKEN = "test-token"


@pytest.fixture(autouse=True)
def use_test_remote_config(monkeypatch):
    monkeypatch.setattr(process_transactions, "REMOTE_API_URL", TEST_REMOTE_URL)
    monkeypatch.setattr(process_transactions, "API_TOKEN", TEST_TOKEN)
    yield


def make_response(status_code):
    res = MagicMock()
    res.status_code = status_code
    if status_code >= 400 and status_code != 409:
        res.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
    else:
        res.raise_for_status.side_effect = None
    return res


class TestPushTransactions:
    def test_counts_created_transactions(self):
        with patch("backend.process_transactions.requests.post", return_value=make_response(201)) as mock_post:
            inserted = push_transactions([{"type": "purchase", "amount": 10.0, "date": "2026-01-01"}])
        assert inserted == 1
        mock_post.assert_called_once()

    def test_skips_duplicates_without_error(self):
        with patch("backend.process_transactions.requests.post", return_value=make_response(409)):
            inserted = push_transactions([{"type": "purchase", "amount": 10.0, "date": "2026-01-01"}])
        assert inserted == 0

    def test_mixed_batch_counts_only_created(self):
        responses = [make_response(201), make_response(409), make_response(201)]
        with patch("backend.process_transactions.requests.post", side_effect=responses):
            inserted = push_transactions([
                {"type": "purchase", "amount": 1.0, "date": "2026-01-01"},
                {"type": "purchase", "amount": 2.0, "date": "2026-01-02"},
                {"type": "purchase", "amount": 3.0, "date": "2026-01-03"},
            ])
        assert inserted == 2

    def test_raises_on_server_error(self):
        with patch("backend.process_transactions.requests.post", return_value=make_response(500)):
            with pytest.raises(requests.HTTPError):
                push_transactions([{"type": "purchase", "amount": 10.0, "date": "2026-01-01"}])

    def test_raises_on_unauthorized(self):
        with patch("backend.process_transactions.requests.post", return_value=make_response(401)):
            with pytest.raises(requests.HTTPError):
                push_transactions([{"type": "purchase", "amount": 10.0, "date": "2026-01-01"}])

    def test_empty_list_returns_zero_without_requests(self):
        with patch("backend.process_transactions.requests.post") as mock_post:
            inserted = push_transactions([])
        assert inserted == 0
        mock_post.assert_not_called()

    def test_sends_bearer_token_and_correct_url(self):
        with patch("backend.process_transactions.requests.post", return_value=make_response(201)) as mock_post:
            push_transactions([{"type": "purchase", "amount": 10.0, "date": "2026-01-01"}])
        args, kwargs = mock_post.call_args
        assert args[0] == f"{TEST_REMOTE_URL}/api/transactions"
        assert kwargs["headers"]["Authorization"] == f"Bearer {TEST_TOKEN}"

    def test_sends_transaction_payload_as_json(self):
        tx = {"type": "purchase", "amount": 10.0, "date": "2026-01-01", "merchant": "OXXO"}
        with patch("backend.process_transactions.requests.post", return_value=make_response(201)) as mock_post:
            push_transactions([tx])
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == tx

    def test_continues_pushing_after_duplicate(self):
        """A 409 mid-batch should not stop later transactions from being sent."""
        responses = [make_response(409), make_response(201)]
        with patch("backend.process_transactions.requests.post", side_effect=responses) as mock_post:
            inserted = push_transactions([
                {"type": "purchase", "amount": 1.0, "date": "2026-01-01"},
                {"type": "purchase", "amount": 2.0, "date": "2026-01-02"},
            ])
        assert inserted == 1
        assert mock_post.call_count == 2


class TestMainUsesRemoteSinkWhenConfigured:
    def test_main_pushes_when_remote_url_set(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "fetch_santander", lambda: [
            {"type": "purchase", "amount": 10.0, "date": "2026-01-01"},
        ])
        monkeypatch.setattr(process_transactions, "save_santander_last_run", lambda: None)
        with patch("backend.process_transactions.push_transactions", return_value=1) as mock_push, \
             patch("backend.process_transactions.insert_transactions") as mock_insert:
            process_transactions.main()
        mock_push.assert_called_once()
        mock_insert.assert_not_called()

    def test_main_uses_local_db_when_remote_url_unset(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", None)
        monkeypatch.setattr(process_transactions, "fetch_santander", lambda: [
            {"type": "purchase", "amount": 10.0, "date": "2026-01-01"},
        ])
        monkeypatch.setattr(process_transactions, "save_santander_last_run", lambda: None)
        monkeypatch.setattr(process_transactions, "init_db", lambda: None)
        monkeypatch.setattr(process_transactions, "get_summary", lambda: {})
        with patch("backend.process_transactions.push_transactions") as mock_push, \
             patch("backend.process_transactions.insert_transactions", return_value=1) as mock_insert:
            process_transactions.main()
        mock_insert.assert_called_once()
        mock_push.assert_not_called()
