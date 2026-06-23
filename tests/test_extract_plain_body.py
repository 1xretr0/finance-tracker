import base64
from backend.banks.santander import _extract_plain_body


def _encode(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("latin-1")).decode()


class TestExtractPlainBody:
    def test_simple_text_plain_payload(self):
        payload = {
            "mimeType": "text/plain",
            "body": {"data": _encode("Hello world")},
        }
        assert _extract_plain_body(payload) == "Hello world"

    def test_multipart_alternative(self):
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _encode("plain text body")}},
                {"mimeType": "text/html", "body": {"data": _encode("<p>html</p>")}},
            ],
        }
        assert _extract_plain_body(payload) == "plain text body"

    def test_nested_multipart_related_then_alternative(self):
        """Simulates: multipart/related > multipart/alternative > text/plain"""
        payload = {
            "mimeType": "multipart/related",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": _encode("nested plain")}},
                        {"mimeType": "text/html", "body": {"data": _encode("<p>html</p>")}},
                    ],
                },
                {"mimeType": "image/gif", "body": {"data": ""}},
            ],
        }
        assert _extract_plain_body(payload) == "nested plain"

    def test_deeply_nested(self):
        """Three levels deep: mixed > related > alternative > text/plain"""
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/related",
                    "parts": [
                        {
                            "mimeType": "multipart/alternative",
                            "parts": [
                                {"mimeType": "text/plain", "body": {"data": _encode("deep body")}},
                                {"mimeType": "text/html", "body": {"data": _encode("<b>hi</b>")}},
                            ],
                        },
                    ],
                },
                {"mimeType": "application/pdf", "body": {"attachmentId": "abc123"}},
            ],
        }
        assert _extract_plain_body(payload) == "deep body"

    def test_returns_none_when_no_text_plain(self):
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/html", "body": {"data": _encode("<p>only html</p>")}},
            ],
        }
        assert _extract_plain_body(payload) is None

    def test_returns_none_for_empty_body_data(self):
        payload = {
            "mimeType": "text/plain",
            "body": {"data": ""},
        }
        assert _extract_plain_body(payload) is None

    def test_skips_text_plain_with_no_data(self):
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": ""}},
                {"mimeType": "text/plain", "body": {"data": _encode("second plain")}},
            ],
        }
        assert _extract_plain_body(payload) == "second plain"

    def test_prefers_first_text_plain_found_in_bfs_order(self):
        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _encode("first")}},
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": _encode("second")}},
                    ],
                },
            ],
        }
        assert _extract_plain_body(payload) == "first"
