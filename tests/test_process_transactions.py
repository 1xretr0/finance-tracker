# ---------------------------------------------------------------------------
# Tests for the remote-push transaction sink
# ---------------------------------------------------------------------------
import logging
from unittest.mock import patch, MagicMock

import pytest
import requests

import backend.process_transactions as process_transactions
from backend.process_transactions import push_transactions, push_transactions_detailed

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

    def test_counts_ignored_separately_from_duplicates(self):
        responses = [make_response(201), make_response(200), make_response(409)]
        with patch("backend.process_transactions.requests.post", side_effect=responses):
            result = push_transactions_detailed([
                {"type": "purchase", "amount": 1.0, "date": "2026-01-01"},
                {"type": "transfer", "amount": 2.0, "date": "2026-01-02"},
                {"type": "purchase", "amount": 3.0, "date": "2026-01-03"},
            ])
        assert result == {"inserted": 1, "ignored": 1, "duplicates": 1}

    def test_ignored_response_not_counted_as_inserted(self):
        with patch("backend.process_transactions.requests.post", return_value=make_response(200)):
            inserted = push_transactions([{"type": "transfer", "amount": 10.0, "date": "2026-01-01"}])
        assert inserted == 0


class TestMainUsesRemoteSinkWhenConfigured:
    def test_main_pushes_when_remote_url_set(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "fetch_santander", lambda since_epoch, interactive=True: [
            {"type": "purchase", "amount": 10.0, "date": "2026-01-01"},
        ])
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: None)
        with patch(
            "backend.process_transactions.push_transactions_detailed",
            return_value={"inserted": 1, "ignored": 0, "duplicates": 0},
        ) as mock_push, patch("backend.process_transactions.insert_transactions_detailed") as mock_insert:
            process_transactions.main()
        mock_push.assert_called_once()
        mock_insert.assert_not_called()

    def test_main_uses_local_db_when_remote_url_unset(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", None)
        monkeypatch.setattr(process_transactions, "fetch_santander", lambda since_epoch, interactive=True: [
            {"type": "purchase", "amount": 10.0, "date": "2026-01-01"},
        ])
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: None)
        monkeypatch.setattr(process_transactions, "init_db", lambda: None)
        monkeypatch.setattr(process_transactions, "get_summary", lambda: {})
        with patch("backend.process_transactions.push_transactions_detailed") as mock_push, \
             patch(
                 "backend.process_transactions.insert_transactions_detailed",
                 return_value={"inserted": 1, "ignored": 0, "duplicates": 0},
             ) as mock_insert:
            process_transactions.main()
        mock_insert.assert_called_once()
        mock_push.assert_not_called()

    def test_main_logs_ignored_separately_from_duplicates(self, monkeypatch, caplog):
        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", None)
        monkeypatch.setattr(process_transactions, "fetch_santander", lambda since_epoch, interactive=True: [
            {"type": "purchase", "amount": 1.0, "date": "2026-01-01"},
            {"type": "purchase", "amount": 2.0, "date": "2026-01-02"},
            {"type": "transfer", "amount": 3.0, "date": "2026-01-03"},
        ])
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: None)
        monkeypatch.setattr(process_transactions, "init_db", lambda: None)
        monkeypatch.setattr(process_transactions, "get_summary", lambda: {})
        monkeypatch.setattr(
            process_transactions,
            "insert_transactions_detailed",
            lambda txs: {"inserted": 1, "ignored": 1, "duplicates": 1},
        )
        with caplog.at_level(logging.INFO):
            process_transactions.main()
        assert "1 new transaction(s) saved (1 duplicates skipped, 1 internal transfers ignored)" in caplog.text


# ---------------------------------------------------------------------------
# Tests for the DB-derived ingestion cursor (replaces the per-bank last-run
# file: backend/banks/santander_last_run.txt)
# ---------------------------------------------------------------------------
class TestComputeSince:
    def test_returns_none_when_no_prior_data(self):
        assert process_transactions._compute_since(None) is None

    def test_subtracts_overlap_window_from_latest_date(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        since_epoch = process_transactions._compute_since("2026-06-20T10:00:00")
        expected = datetime(2026, 6, 20, 10, 0, 0, tzinfo=ZoneInfo("America/Mexico_City"))
        expected -= timedelta(hours=process_transactions.SYNC_OVERLAP_HOURS)
        assert since_epoch == int(expected.timestamp())

    def test_result_is_before_the_latest_date(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        since_epoch = process_transactions._compute_since("2026-06-20T10:00:00")
        latest_epoch = int(
            datetime(2026, 6, 20, 10, 0, 0, tzinfo=ZoneInfo("America/Mexico_City")).timestamp()
        )
        assert since_epoch < latest_epoch


class TestGetLatestDate:
    def test_remote_mode_reads_from_status_endpoint(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", TEST_REMOTE_URL)
        res = MagicMock()
        res.status_code = 200
        res.json.return_value = {"latest_tx_dates": {"santander": "2026-06-20T10:00:00"}}
        with patch("backend.process_transactions.requests.get", return_value=res) as mock_get:
            latest = process_transactions.get_latest_date("santander")
        assert latest == "2026-06-20T10:00:00"
        args, kwargs = mock_get.call_args
        assert args[0] == f"{TEST_REMOTE_URL}/api/status"
        assert kwargs["headers"]["Authorization"] == f"Bearer {TEST_TOKEN}"

    def test_remote_mode_raises_when_server_unreachable(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", TEST_REMOTE_URL)
        with patch(
            "backend.process_transactions.requests.get",
            side_effect=requests.ConnectionError("refused"),
        ):
            with pytest.raises(requests.ConnectionError):
                process_transactions.get_latest_date("santander")

    def test_local_mode_reads_from_storage(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", None)
        with patch(
            "backend.process_transactions.get_latest_tx_date", return_value="2026-05-01T00:00:00"
        ) as mock_get_latest:
            latest = process_transactions.get_latest_date("santander")
        assert latest == "2026-05-01T00:00:00"
        mock_get_latest.assert_called_once_with(process_transactions.SOURCE_BANKS["santander"])


class TestRunSync:
    def test_local_mode_fetches_since_derived_cursor_and_inserts(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", None)
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: None)
        fetch_mock = MagicMock(return_value=[{"type": "purchase", "amount": 1.0, "date": "2026-01-01"}])
        monkeypatch.setattr(process_transactions, "fetch_santander", fetch_mock)
        with patch(
            "backend.process_transactions.insert_transactions_detailed",
            return_value={"inserted": 1, "ignored": 0, "duplicates": 0},
        ) as mock_insert:
            result = process_transactions.run_sync(use_remote=False)
        assert result == {"inserted": 1, "ignored": 0, "duplicates": 0}
        fetch_mock.assert_called_once_with(None, interactive=True)
        mock_insert.assert_called_once()

    def test_defaults_to_interactive_fetch_when_unspecified(self, monkeypatch):
        """CLI usage (process_transactions.main()) keeps the interactive OAuth
        flow available by default; only the server opts out."""
        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", None)
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: None)
        fetch_mock = MagicMock(return_value=[])
        monkeypatch.setattr(process_transactions, "fetch_santander", fetch_mock)
        process_transactions.run_sync(use_remote=False)
        fetch_mock.assert_called_once_with(None, interactive=True)

    def test_forwards_interactive_false_to_fetch(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", None)
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: None)
        fetch_mock = MagicMock(return_value=[])
        monkeypatch.setattr(process_transactions, "fetch_santander", fetch_mock)
        process_transactions.run_sync(use_remote=False, interactive=False)
        fetch_mock.assert_called_once_with(None, interactive=False)

    def test_propagates_authentication_required_error(self, monkeypatch):
        """A non-interactive run with no refreshable token can't silently
        swallow the failure into a zero-count result — the caller (the
        server's /api/sync handler) needs to tell it apart to return 503."""
        from backend.banks.santander import AuthenticationRequiredError

        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", None)
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: None)

        def raise_auth_error(since_epoch, interactive=True):
            raise AuthenticationRequiredError("no valid token")

        monkeypatch.setattr(process_transactions, "fetch_santander", raise_auth_error)
        with pytest.raises(AuthenticationRequiredError):
            process_transactions.run_sync(use_remote=False, interactive=False)

    def test_remote_mode_fetches_since_derived_cursor_and_pushes(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: "2026-06-20T10:00:00")
        fetch_mock = MagicMock(return_value=[{"type": "purchase", "amount": 1.0, "date": "2026-06-21"}])
        monkeypatch.setattr(process_transactions, "fetch_santander", fetch_mock)
        with patch(
            "backend.process_transactions.push_transactions_detailed",
            return_value={"inserted": 1, "ignored": 0, "duplicates": 0},
        ) as mock_push:
            result = process_transactions.run_sync(use_remote=True)
        assert result == {"inserted": 1, "ignored": 0, "duplicates": 0}
        since_epoch = fetch_mock.call_args[0][0]
        assert since_epoch is not None
        mock_push.assert_called_once()

    def test_aborts_without_fetching_when_cursor_lookup_fails(self, monkeypatch):
        def raise_connection_error(source):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(process_transactions, "get_latest_date", raise_connection_error)
        fetch_mock = MagicMock()
        monkeypatch.setattr(process_transactions, "fetch_santander", fetch_mock)
        result = process_transactions.run_sync(use_remote=True)
        assert result is None
        fetch_mock.assert_not_called()

    def test_returns_zero_counts_when_nothing_fetched(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: None)
        monkeypatch.setattr(process_transactions, "fetch_santander", lambda since_epoch, interactive=True: [])
        result = process_transactions.run_sync(use_remote=False)
        assert result == {"inserted": 0, "ignored": 0, "duplicates": 0}

    def test_returns_none_when_fetch_fails(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: None)

        def raise_fetch_error(since_epoch):
            raise RuntimeError("Gmail API error")

        monkeypatch.setattr(process_transactions, "fetch_santander", raise_fetch_error)
        with patch("backend.process_transactions.insert_transactions_detailed") as mock_insert:
            result = process_transactions.run_sync(use_remote=False)
        assert result is None
        mock_insert.assert_not_called()

    def test_returns_none_when_save_fails(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: None)
        monkeypatch.setattr(process_transactions, "fetch_santander", lambda since_epoch: [
            {"type": "purchase", "amount": 1.0, "date": "2026-01-01"},
        ])
        with patch(
            "backend.process_transactions.insert_transactions_detailed",
            side_effect=RuntimeError("db locked"),
        ):
            result = process_transactions.run_sync(use_remote=False)
        assert result is None

    def test_remote_mode_cursor_matches_compute_since(self, monkeypatch):
        """The epoch handed to fetch_santander must be _compute_since's output
        for the derived latest date, not merely non-None."""
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: "2026-06-20T10:00:00")
        fetch_mock = MagicMock(return_value=[])
        monkeypatch.setattr(process_transactions, "fetch_santander", fetch_mock)
        process_transactions.run_sync(use_remote=True)
        expected = process_transactions._compute_since("2026-06-20T10:00:00")
        fetch_mock.assert_called_once_with(expected, interactive=True)

    def test_logs_traceback_on_cursor_failure(self, monkeypatch, caplog):
        def raise_connection_error(source):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(process_transactions, "get_latest_date", raise_connection_error)
        with caplog.at_level(logging.ERROR):
            process_transactions.run_sync(use_remote=True)
        exc_records = [r for r in caplog.records if r.exc_info is not None]
        assert exc_records, "expected a log record with a captured traceback"


class TestMainExitsOnFailure:
    def test_main_exits_nonzero_when_sync_fails(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", None)
        monkeypatch.setattr(process_transactions, "init_db", lambda: None)

        def raise_cursor_error(source):
            raise RuntimeError("boom")

        monkeypatch.setattr(process_transactions, "get_latest_date", raise_cursor_error)
        with pytest.raises(SystemExit) as exc_info:
            process_transactions.main()
        assert exc_info.value.code == 1

    def test_main_does_not_exit_when_sync_succeeds(self, monkeypatch):
        monkeypatch.setattr(process_transactions, "REMOTE_API_URL", None)
        monkeypatch.setattr(process_transactions, "init_db", lambda: None)
        monkeypatch.setattr(process_transactions, "get_summary", lambda: {})
        monkeypatch.setattr(process_transactions, "get_latest_date", lambda source: None)
        monkeypatch.setattr(process_transactions, "fetch_santander", lambda since_epoch, interactive=True: [])
        process_transactions.main()
