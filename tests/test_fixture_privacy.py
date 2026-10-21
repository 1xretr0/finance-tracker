# ---------------------------------------------------------------------------
# Guards the Gmail payload fixtures against personal data. The payloads were
# copied from real Gmail API responses, so anything that identifies the
# recipient must stay masked in the base64 bodies.
# ---------------------------------------------------------------------------
import base64
import re

import pytest

from tests import test_santander_parser_gmail as gmail_fixtures

PAYLOADS = {
    name: payload
    for name, payload in vars(gmail_fixtures).items()
    if name.endswith("_PAYLOAD")
}


def _decoded(payload):
    data = payload["body"]["data"]
    # latin-1 maps every byte, so the iso-8859-1 fixture decodes like the UTF-8 ones
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("latin-1")


def test_payload_fixtures_were_discovered():
    assert len(PAYLOADS) >= 4


@pytest.mark.parametrize("name", sorted(PAYLOADS))
class TestGmailFixturesAreAnonymised:
    def test_only_example_or_bank_email_addresses(self, name):
        for address in re.findall(r"[\w.+-]+@[\w.-]+", _decoded(PAYLOADS[name])):
            domain = address.rsplit("@", 1)[1].rstrip(".").lower()
            assert domain == "example.com" or domain.endswith("santander.com.mx"), address

    def test_no_recipient_specific_tracking_tokens(self, name):
        assert not re.search(r"\?qs=(?!EXAMPLE)", _decoded(PAYLOADS[name]))

    def test_no_account_holder_surname(self, name):
        assert "moran" not in _decoded(PAYLOADS[name]).lower()
