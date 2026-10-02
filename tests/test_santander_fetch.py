# ---------------------------------------------------------------------------
# Tests for Santander Gmail fetch orchestration: stateless cursor (since_epoch
# passed in by the caller instead of a per-client last-run file) and pagination.
# ---------------------------------------------------------------------------
from unittest.mock import patch

import backend.banks.santander as santander
from backend.banks.santander import fetch_transactions

PURCHASE_EMAIL = """\
Te informamos que se autorizó una compra con tu tarjeta de crédito terminación: 8949.

Monto:
$618.20 MXN

Comercio:
VIPS LEGARIA

Fecha y hora:
15/06/2026 15:01:07 hrs
"""


def _plain_text_payload(text: str) -> dict:
    import base64
    data = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")
    return {
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "Subject", "value": "test"}],
            "body": {"data": data},
        }
    }


class FakeMessagesResource:
    """Mimics service.users().messages() for list()/get(), paginating via
    nextPageToken the way the real Gmail API does."""

    def __init__(self, pages: list[dict], bodies: dict[str, dict]):
        self.pages = pages
        self.bodies = bodies
        self.list_calls = []

    def list(self, userId, q, maxResults, pageToken=None):
        self.list_calls.append({"q": q, "pageToken": pageToken})
        page = self.pages[len(self.list_calls) - 1]
        return _Executable(page)

    def get(self, userId, id, format):
        return _Executable(self.bodies[id])


class _Executable:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class FakeService:
    def __init__(self, messages_resource):
        self._messages_resource = messages_resource

    def users(self):
        return self

    def messages(self):
        return self._messages_resource


def _patch_gmail(pages, bodies, authenticate=None):
    fake_messages = FakeMessagesResource(pages, bodies)
    fake_service = FakeService(fake_messages)
    return fake_messages, patch.multiple(
        santander,
        build=lambda *a, **kw: fake_service,
        _authenticate=authenticate or (lambda interactive=True: None),
    )


class TestSinceEpochQuery:
    def test_omits_after_filter_when_since_epoch_is_none(self):
        fake_messages, patcher = _patch_gmail(
            pages=[{"messages": []}], bodies={}
        )
        with patcher:
            fetch_transactions(since_epoch=None)
        assert "after:" not in fake_messages.list_calls[0]["q"]

    def test_adds_after_filter_when_since_epoch_given(self):
        fake_messages, patcher = _patch_gmail(
            pages=[{"messages": []}], bodies={}
        )
        with patcher:
            fetch_transactions(since_epoch=1700000000)
        assert "after:1700000000" in fake_messages.list_calls[0]["q"]

    def test_defaults_to_full_fetch_with_no_argument(self):
        """fetch_transactions() with no args behaves like since_epoch=None."""
        fake_messages, patcher = _patch_gmail(
            pages=[{"messages": []}], bodies={}
        )
        with patcher:
            fetch_transactions()
        assert "after:" not in fake_messages.list_calls[0]["q"]


class TestPagination:
    def test_follows_next_page_token_until_exhausted(self):
        bodies = {
            "m1": _plain_text_payload(PURCHASE_EMAIL),
            "m2": _plain_text_payload(PURCHASE_EMAIL),
        }
        pages = [
            {"messages": [{"id": "m1"}], "nextPageToken": "page2"},
            {"messages": [{"id": "m2"}]},
        ]
        fake_messages, patcher = _patch_gmail(pages, bodies)
        with patcher:
            transactions = fetch_transactions(since_epoch=None)
        assert len(transactions) == 2
        assert len(fake_messages.list_calls) == 2
        assert fake_messages.list_calls[1]["pageToken"] == "page2"

    def test_stops_when_no_next_page_token(self):
        fake_messages, patcher = _patch_gmail(
            pages=[{"messages": [{"id": "m1"}]}],
            bodies={"m1": _plain_text_payload(PURCHASE_EMAIL)},
        )
        with patcher:
            fetch_transactions(since_epoch=None)
        assert len(fake_messages.list_calls) == 1

    def test_single_page_still_returns_all_transactions(self):
        fake_messages, patcher = _patch_gmail(
            pages=[{"messages": [{"id": "m1"}, {"id": "m2"}]}],
            bodies={
                "m1": _plain_text_payload(PURCHASE_EMAIL),
                "m2": _plain_text_payload(PURCHASE_EMAIL),
            },
        )
        with patcher:
            transactions = fetch_transactions()
        assert len(transactions) == 2

    def test_unparsable_message_is_skipped_and_later_pages_still_processed(self):
        """A message that fails to parse (e.g. an unrecognized notification
        format) must not abort the fetch or truncate later pages."""
        unparsable_body = _plain_text_payload("Some unrelated notification with no transaction data.")
        bodies = {
            "m1": unparsable_body,
            "m2": _plain_text_payload(PURCHASE_EMAIL),
        }
        pages = [
            {"messages": [{"id": "m1"}], "nextPageToken": "page2"},
            {"messages": [{"id": "m2"}]},
        ]
        fake_messages, patcher = _patch_gmail(pages, bodies)
        with patcher:
            transactions = fetch_transactions(since_epoch=None)
        assert len(transactions) == 1
        assert len(fake_messages.list_calls) == 2


class TestInteractiveFlag:
    """The server (Phase 2) calls fetch_transactions(interactive=False) so a
    sync request never blocks on an interactive OAuth browser flow."""

    def test_defaults_to_interactive_authentication(self):
        calls = []
        fake_messages, patcher = _patch_gmail(
            pages=[{"messages": []}],
            bodies={},
            authenticate=lambda interactive=True: calls.append(interactive),
        )
        with patcher:
            fetch_transactions(since_epoch=None)
        assert calls == [True]

    def test_forwards_interactive_false_to_authenticate(self):
        calls = []
        fake_messages, patcher = _patch_gmail(
            pages=[{"messages": []}],
            bodies={},
            authenticate=lambda interactive=True: calls.append(interactive),
        )
        with patcher:
            fetch_transactions(since_epoch=None, interactive=False)
        assert calls == [False]
>>>>>>> f13c0bd (test: add reproducer for dashboard-triggered sync (interactive auth flag, /api/sync, TOKEN_PATH))
