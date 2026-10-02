# ---------------------------------------------------------------------------
# Tests for Santander Gmail OAuth authentication, specifically the
# interactive flag added for Phase 2 ("Sync now" from the dashboard): the
# server must never trigger InstalledAppFlow.run_local_server, since there's
# no browser to complete that flow on a headless host.
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock, patch

import pytest

import backend.banks.santander as santander
from backend.banks.santander import AuthenticationRequiredError, _authenticate


@pytest.fixture(autouse=True)
def no_real_token_file(tmp_path, monkeypatch):
    """Point TOKEN_FILE at a path that doesn't exist by default, so tests
    don't depend on (or clobber) a real local token.json."""
    monkeypatch.setattr(santander, "TOKEN_FILE", str(tmp_path / "token.json"))
    yield


class TestInteractiveAuthentication:
    def test_runs_interactive_flow_when_no_token_and_interactive_true(self):
        fake_creds = MagicMock(valid=True)
        fake_creds.to_json.return_value = "{}"
        fake_flow = MagicMock()
        fake_flow.run_local_server.return_value = fake_creds
        with patch.object(
            santander.InstalledAppFlow, "from_client_secrets_file", return_value=fake_flow
        ) as mock_from_secrets:
            creds = _authenticate(interactive=True)
        mock_from_secrets.assert_called_once()
        fake_flow.run_local_server.assert_called_once()
        assert creds is fake_creds

    def test_refreshes_expired_token_without_needing_interactive(self, tmp_path):
        token_path = tmp_path / "token.json"
        token_path.write_text("{}")
        santander.TOKEN_FILE = str(token_path)

        expired_creds = MagicMock(valid=False, expired=True, refresh_token="refresh-tok")
        expired_creds.to_json.return_value = "{}"
        with patch.object(
            santander.Credentials, "from_authorized_user_file", return_value=expired_creds
        ), patch.object(santander.Request, "__init__", return_value=None):
            creds = _authenticate(interactive=False)
        expired_creds.refresh.assert_called_once()
        assert creds is expired_creds


class TestNonInteractiveAuthentication:
    def test_raises_when_no_token_and_interactive_false(self):
        with pytest.raises(AuthenticationRequiredError):
            _authenticate(interactive=False)

    def test_raises_when_token_invalid_and_not_refreshable_and_interactive_false(self, tmp_path):
        token_path = tmp_path / "token.json"
        token_path.write_text("{}")
        santander.TOKEN_FILE = str(token_path)

        unrefreshable_creds = MagicMock(valid=False, expired=False, refresh_token=None)
        with patch.object(
            santander.Credentials, "from_authorized_user_file", return_value=unrefreshable_creds
        ):
            with pytest.raises(AuthenticationRequiredError):
                _authenticate(interactive=False)

    def test_never_calls_interactive_flow_when_interactive_false(self):
        with patch.object(santander.InstalledAppFlow, "from_client_secrets_file") as mock_from_secrets:
            with pytest.raises(AuthenticationRequiredError):
                _authenticate(interactive=False)
        mock_from_secrets.assert_not_called()
