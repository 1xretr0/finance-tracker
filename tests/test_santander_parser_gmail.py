# ---------------------------------------------------------------------------
# Tests for Santander email parsers using real Gmail API payload structure
# ---------------------------------------------------------------------------
"""
This test file uses actual base64-encoded email bodies extracted from Gmail API
responses to test the complete pipeline: extraction → decoding → parsing.

This ensures we're testing with the same data format that Gmail actually delivers.
"""
from backend.banks.santander import _extract_plain_body, parse_transaction
from backend.constants import BANK_SANTANDER_LIKEU, BANK_SANTANDER, BANK_SANTANDER_GOLD

# ---------------------------------------------------------------------------
# Real Gmail API payload data (base64-encoded, extracted from actual responses)
# ---------------------------------------------------------------------------

# Transfer confirmation email (field-style)
TRANSFER_CONFIRMATION_PAYLOAD = {
    "mimeType": "text/plain",
    "body": {
        "data": "DQpfX19fX19fX19fX19fX19fX19fX19fX19fX19fX19fXw0KRnJvbTogU2FudGFuZGVyIDxzYW50YW5kZXJAZW52aW8uc2FudGFuZGVyLmNvbS5teD4NClNlbnQ6IFdlZG5lc2RheSwgQXVndXN0IDUsIDIwMjYgMDg6MzcgQU0NClRvOiBTRUJBU01PUkFOREVaQEhPVE1BSUwuQ09NIDxTRUJBU01PUkFOREVaQEhPVE1BSUwuQ09NPg0KU3ViamVjdDogQ29uZmlybWFjacOzbiBkZSB0cmFuc2ZlcmVuY2lhDQoNCg0KDQpTaSBubyBwdWVkZXMgdmVyIGVzdGUgbWVuc2FqZSBjb3JyZWN0YW1lbnRlIGhheiBjbGljICBhcXXDrTxodHRwczovL2NsaWNrLmVudmlvLnNhbnRhbmRlci5jb20ubXgvP3FzPUFCQjdJbllpT2pFc0ltUWlPalE1TlRsOUFBb0FBQUFBQTE0RjdBWGFPOXJQZnNxWnhHY0JLNGcxcUJfRjRqTExrVWlaTElKRkRWTUFLZEFMOXk1anhZUkc3czVCVnZ5Ukg0VlFGSTlQaWxCY3pnNjBuRHF5cWt0WjUyamRubmtodGh0Q0FwcW8tMXM-DQoNCltTYW50YW5kZXJdDQowNS8wOC8yMDI2DQoNCkNvbmZpcm1hY2nDs24gZGUgdHJhbnNmZXJlbmNpYQ0KDQpFc3RpbWFkbyBjbGllbnRlLCByZWFsaXphc3RlIHVuYSB0cmFuc2ZlcmVuY2lhIGRlIHR1IGN1ZW50YSB0ZXJtaW5hY2nDs24gNjQ2NiBhIGxhIGN1ZW50YSB0ZXJtaW5hY2nDs24gMTMwNiBlbiBCQlZBIE1FWElDTy4NCg0KRGV0YWxsZXMgZGUgbGEgb3BlcmFjacOzbg0KDQoNCg0KSW1wb3J0ZTogJDQsNjY5LjAwIE1YUA0KRmVjaGE6IDA1LzA4LzIwMjYNCkhvcmE6IDA4OjM3IGhycw0KUmVmZXJlbmNpYTogNjM4NTUyOQ0KDQrCv05vIHJlY29ub2NlcyBlc3RhIG9wZXJhY2nDs24_IENvbXVuw61jYXRlIGRlIGlubWVkaWF0byBhIFN1cGVyTMOtbmVhDQo1NSA1MTY5IDQzMDMuDQoNClBhcmEgbWF5b3IgaW5mb3JtYWNpw7NuIHNvYnJlIGxvcyByZXF1aXNpdG9zLCBjb21pc2lvbmVzIHkgY29uZGljaW9uZXMgZGUgY29udHJhdGFjacOzbiBkZSBsb3MgcHJvZHVjdG9zIHkgc2VydmljaW9zIGRlIFNhbnRhbmRlciwgYXPDrSBjb21vIG51ZXN0cm8gQXZpc28gZGUgUHJpdmFjaWRhZCwgY29uc3VsdGFyIHd3dy5zYW50YW5kZXIuY29tLm14"
    }
}

# Outgoing transfer narrative email
OUTGOING_TRANSFER_PAYLOAD = {
    "mimeType": "text/plain",
    "body": {
        "data": "DQpfX19fX19fX19fX19fX19fX19fX19fX19fX19fX19fXw0KRnJvbTogQXZpc29zIFNhbnRhbmRlciA8bm90aWZpY2FjaW9uZXNAbm90aWZpY2FjaW9uZXMuc2FudGFuZGVyLmNvbS5teD4NClNlbnQ6IFdlZG5lc2RheSwgSnVseSA4LCAyMDI2IDAxOjM1IFBNDQpUbzogU0VCQVNUSUFOIE1PUkFOIEhFUk5BTkRFWiA8U0VCQVNNT1JBTkRFWkBIT1RNQUlMLkNPTT4NClN1YmplY3Q6IE5vdGlmaWNhY2nDs24gVHJhbnNmZXJlbmNpYSBJbnRlcmJhbmNhcmlhIGEgdHJhdsOpcyBkZSBTdXBlck3Ds3ZpbC4NCg0KW2NpZDp2bXFla2V3YmdmXQ0KDQoNCkFwcmVjaWFibGUgU0VCQVNUSUFOIE1PUkFOIEhFUk5BTkRFWg0KDQpMZSBpbmZvcm1hbW9zIHF1ZSByZWNpYmltb3Mgc3Ugc29saWNpdHVkIHBhcmEgcmVhbGl6YXIgdW5hIHRyYW5zZmVyZW5jaWEsIGRlIHN1IGN1ZW50YSB0ZXJtaW5hY2nDs24gNjQ2NiwgYSBsYSBjdWVudGEgdGVybWluYWNpw7NuIDAzNzYgZW4gSFNCQyBwb3IgdW4gaW1wb3J0ZSBkZSAkIDkwLjAwIGVsIDA4L0p1bC8yMDI2IGEgbGFzIDEzOjM1LCBjb24gbGEgcmVmZXJlbmNpYSA3OTQ4MTcwLg=="
    }
}

# Unique Points purchase email
UNIQUE_POINTS_PAYLOAD = {
    "mimeType": "text/plain",
    "body": {
        "data": "DQoNCl9fX19fX19fX19fX19fX19fX19fX19fX19fX19fX19fDQpGcm9tOiBTYW50YW5kZXIgPHNhbnRhbmRlckBlbnZpby5zYW50YW5kZXIuY29tLm14Pg0KU2VudDogTW9uZGF5LCBBdWd1c3QgMywgMjAyNiAwNTo0MSBQTQ0KVG86IFNFQkFTTU9SQU5ERVpASE9UTUFJTC5DT00gPFNFQkFTTU9SQU5ERVpASE9UTUFJTC5DT00-DQpTdWJqZWN0OiBUdSBjb21wcmEgdGUgYWNhYmEgZGUgZ2VuZXJhciBVbmlxdWUgUG9pbnRzDQoNCg0KU2kgbm8gcHVlZGVzIHZlciBlc3RlIG1lbnNhamUgY29ycmVjdGFtZW50ZSBoYXogY2xpYyBhcXXDrTxodHRwczovL2NsaWNrLmVudmlvLnNhbnRhbmRlci5jb20ubXgvP3FzPUFCQjdJbllpT2pFc0ltUWlPalE1TlRkOUFBb0FBQUFBQTBmTzRtMW9HY0xRMm9zTGhTcWQ3Y1JLbzdoQW5TVTdmUXQ2b2I0SlFSc05DSEVpbFlFdnkwcTQxOXlzSDlmM1BfNmRvUGFOTWdDUEYyMHpwZ01ubU9ZSlU0MzljcVhjVW5vOXhMTkNIdz4NCltodHRwczovL2ltYWdlLmVudmlvLnNhbnRhbmRlci5jb20ubXgvbGliL2ZlM2IxNTcwNzU2NDAwN2M3MjEyNzEvbS8xLzI1ODQ2MGRiLTUxOWQtNDUzZC1iNWY3LTBlYzYzODBjZTJkNi5qcGddDQoNCkhvbGEsIEVzdGltYWRvIENsaWVudGUuDQoNCjAzLzA4LzIwMjYuDQoNClJlYWxpemFzdGUgdW5hIGNvbXByYSBjb24gdHUgVGFyamV0YSBjcsOpZGl0byB0ZXJtaW5hY2nDs24gNTc4OA0KDQpbaHR0cHM6Ly9pbWFnZS5lbnZpby5zYW50YW5kZXIuY29tLm14L2xpYi9mZTNiMTU3MDc1NjQwMDdjNzIxMjcxL20vMS8xZGRkZGZkMy05YTVmLTRhZDctYTcxMy0yOTMzZWFlYjQxODMuanBnXQ0KDQpUZSBpbmZvcm1hbW9zIHF1ZSBzZSBhdXRvcml6w7MgdW5hIGNvbXByYQ0KZW4gV0wgKlNURUFNIFBVUkNIQVNFIHBvciB1biBtb250bw0KZGUgJDEsOTk5LjAwIE0uTi4="
    }
}

# Unique Points purchase email, newer "MXN" template — the original
# text/plain part declared iso-8859-1 and the raw bytes are NOT valid UTF-8
# once decoded (contains Latin-1 accented chars), exercising the charset
# fallback in _extract_plain_body.
UNIQUE_POINTS_MXN_PAYLOAD = {
    "mimeType": "text/plain",
    "headers": [{"name": "Content-Type", "value": 'text/plain; charset="iso-8859-1"'}],
    "body": {
        "data": "Cl9fX19fX19fX19fX19fX19fX19fX19fX19fX19fX19fCkZyb206IFNhbnRhbmRlciA8bm90aWZpY2FjaW9uQG9wZXJhY2lvbmVzLnNhbnRhbmRlci5jb20ubXg-ClNlbnQ6IFRodXJzZGF5LCBPY3RvYmVyIDEsIDIwMjYgMjo1Nzo1OCBQTSAoVVRDLTA2OjAwKSBHdWFkYWxhamFyYSwgTWV4aWNvIENpdHksIE1vbnRlcnJleQpUbzogc2ViYXNtb3JhbmRlekBob3RtYWlsLmNvbSA8c2ViYXNtb3JhbmRlekBob3RtYWlsLmNvbT4KU3ViamVjdDogVHUgY29tcHJhIHRlIGFjYWJhIGRlIGdlbmVyYXIgVW5pcXVlIFBvaW50cwoKCgpbU2FudGFuZGVyXQowMS8xMC8yMDI2CltTYW50YW5kZXJdCgpSRUFMSVpBU1RFIFVOQSBDT01QUkEgQ09OIFRVIFRBUkpFVEEgREUgY3LpZGl0byBURVJNSU5BQ0nTTiAxMzk3CgpFc3RpbWFkbyBjbGllbnRlLCB0ZSBpbmZvcm1hbW9zIHF1ZSBzZSBhdXRvcml68yB1bmEgY29tcHJhIGVuIFJFU1RBVVJBVCBDQU1PTUlMQSBwb3IgdW4gbW9udG8gZGUgJDI5MS41MCBNWE4uCgpQb3IgZXN0YSB0cmFuc2FjY2nzbiBzZSBzdW1hcuFuIGEgbGEgY3VlbnRhIGRlbCB0aXR1bGFyOiAxNyBVbmlxdWUgUG9pbnQgcXVlIHBvZHLhIHV0aWxpemFyIGVuIFNhbnRhbmRlciBVbmlxdWUgUmV3YXJkcy4K"
    }
}

# ---------------------------------------------------------------------------
# Test suite: Transfer confirmation parser with real Gmail data
# ---------------------------------------------------------------------------
class TestTransferConfirmationWithGmailData:
    def test_extracts_and_parses_correctly(self):
        """Test the full pipeline: extract from Gmail payload → parse transaction."""
        plain_text = _extract_plain_body(TRANSFER_CONFIRMATION_PAYLOAD)
        assert plain_text is not None
        assert "terminación" in plain_text  # Validate UTF-8 decoding worked

        tx = parse_transaction(plain_text)
        assert tx is not None
        assert tx["type"] == "outgoing_transfer"

    def test_parses_amount(self):
        plain_text = _extract_plain_body(TRANSFER_CONFIRMATION_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["amount"] == 4669.00

    def test_parses_source_account(self):
        plain_text = _extract_plain_body(TRANSFER_CONFIRMATION_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["account_last4"] == "6466"

    def test_parses_dest_account(self):
        plain_text = _extract_plain_body(TRANSFER_CONFIRMATION_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["dest_account_last4"] == "1306"

    def test_parses_dest_bank(self):
        plain_text = _extract_plain_body(TRANSFER_CONFIRMATION_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["dest_bank"] == "BBVA MEXICO"

    def test_parses_reference(self):
        plain_text = _extract_plain_body(TRANSFER_CONFIRMATION_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["reference"] == "6385529"

    def test_parses_date(self):
        plain_text = _extract_plain_body(TRANSFER_CONFIRMATION_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["date"] == "2026-08-05T08:37:00"

    def test_bank_is_santander(self):
        plain_text = _extract_plain_body(TRANSFER_CONFIRMATION_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["bank"] == BANK_SANTANDER

    def test_currency_is_mxn(self):
        plain_text = _extract_plain_body(TRANSFER_CONFIRMATION_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["currency"] == "MXN"

# ---------------------------------------------------------------------------
# Test suite: Outgoing transfer narrative with real Gmail data
# ---------------------------------------------------------------------------
class TestOutgoingTransferNarrativeWithGmailData:
    def test_extracts_and_parses_correctly(self):
        """Test the full pipeline: extract from Gmail payload → parse transaction."""
        plain_text = _extract_plain_body(OUTGOING_TRANSFER_PAYLOAD)
        assert plain_text is not None
        assert "terminación" in plain_text  # Validate UTF-8 decoding worked

        tx = parse_transaction(plain_text)
        assert tx is not None
        assert tx["type"] == "outgoing_transfer"

    def test_parses_amount(self):
        plain_text = _extract_plain_body(OUTGOING_TRANSFER_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["amount"] == 90.00

    def test_parses_source_account(self):
        plain_text = _extract_plain_body(OUTGOING_TRANSFER_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["account_last4"] == "6466"

    def test_parses_dest_account(self):
        plain_text = _extract_plain_body(OUTGOING_TRANSFER_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["dest_account_last4"] == "0376"

    def test_parses_dest_bank(self):
        plain_text = _extract_plain_body(OUTGOING_TRANSFER_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["dest_bank"] == "HSBC"

    def test_parses_reference(self):
        plain_text = _extract_plain_body(OUTGOING_TRANSFER_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["reference"] == "7948170"

    def test_parses_date(self):
        plain_text = _extract_plain_body(OUTGOING_TRANSFER_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["date"] == "2026-07-08T13:35:00"

# ---------------------------------------------------------------------------
# Test suite: Unique Points purchase with real Gmail data
# ---------------------------------------------------------------------------
class TestUniquePointsPurchaseWithGmailData:
    def test_extracts_and_parses_correctly(self):
        """Test the full pipeline: extract from Gmail payload → parse transaction."""
        plain_text = _extract_plain_body(UNIQUE_POINTS_PAYLOAD)
        assert plain_text is not None
        assert "crédito" in plain_text  # Validate UTF-8 decoding worked

        tx = parse_transaction(plain_text)
        assert tx is not None
        assert tx["type"] == "purchase"

    def test_parses_amount(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["amount"] == 1999.00

    def test_parses_merchant(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["merchant"] == "WL *STEAM PURCHASE"

    def test_parses_card_last4(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["card_last4"] == "5788"

    def test_parses_date(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["date"] == "2026-08-03T00:00:00"

    def test_bank_is_santander(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["bank"] == BANK_SANTANDER_GOLD

    def test_currency_is_mxn(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["currency"] == "MXN"

# ---------------------------------------------------------------------------
# Test suite: Unique Points purchase (newer "MXN" template) with real Gmail
# data — covers the iso-8859-1 charset fallback and uppercase TERMINACIÓN
# ---------------------------------------------------------------------------
class TestUniquePointsPurchaseMxnWithGmailData:
    def test_extracts_and_parses_correctly(self):
        """Test the full pipeline: extract from Gmail payload → parse transaction."""
        plain_text = _extract_plain_body(UNIQUE_POINTS_MXN_PAYLOAD)
        assert plain_text is not None
        assert "crédito" in plain_text  # Validate iso-8859-1 decoding worked

        tx = parse_transaction(plain_text)
        assert tx is not None
        assert tx["type"] == "purchase"

    def test_parses_amount(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_MXN_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["amount"] == 291.50

    def test_parses_merchant(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_MXN_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["merchant"] == "RESTAURAT CAMOMILA"

    def test_parses_card_last4(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_MXN_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["card_last4"] == "1397"

    def test_parses_date(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_MXN_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["date"] == "2026-10-01T00:00:00"

    def test_bank_is_santander(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_MXN_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["bank"] == BANK_SANTANDER_GOLD

    def test_currency_is_mxn(self):
        plain_text = _extract_plain_body(UNIQUE_POINTS_MXN_PAYLOAD)
        tx = parse_transaction(plain_text)
        assert tx["currency"] == "MXN"
