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
        "data": "DQpfX19fX19fX19fX19fX19fX19fX19fX19fX19fX19fXw0KRnJvbTogU2FudGFuZGVyIDxzYW50YW5kZXJAZW52aW8uc2FudGFuZGVyLmNvbS5teD4NClNlbnQ6IFdlZG5lc2RheSwgQXVndXN0IDUsIDIwMjYgMDg6MzcgQU0NClRvOiBKQU5FLkRPRUBFWEFNUExFLkNPTSA8SkFORS5ET0VARVhBTVBMRS5DT00-DQpTdWJqZWN0OiBDb25maXJtYWNpw7NuIGRlIHRyYW5zZmVyZW5jaWENCg0KDQoNClNpIG5vIHB1ZWRlcyB2ZXIgZXN0ZSBtZW5zYWplIGNvcnJlY3RhbWVudGUgaGF6IGNsaWMgIGFxdcOtPGh0dHBzOi8vY2xpY2suZW52aW8uc2FudGFuZGVyLmNvbS5teC8_cXM9RVhBTVBMRT4NCg0KW1NhbnRhbmRlcl0NCjA1LzA4LzIwMjYNCg0KQ29uZmlybWFjacOzbiBkZSB0cmFuc2ZlcmVuY2lhDQoNCkVzdGltYWRvIGNsaWVudGUsIHJlYWxpemFzdGUgdW5hIHRyYW5zZmVyZW5jaWEgZGUgdHUgY3VlbnRhIHRlcm1pbmFjacOzbiA2NDY2IGEgbGEgY3VlbnRhIHRlcm1pbmFjacOzbiAxMzA2IGVuIEJCVkEgTUVYSUNPLg0KDQpEZXRhbGxlcyBkZSBsYSBvcGVyYWNpw7NuDQoNCg0KDQpJbXBvcnRlOiAkNCw2NjkuMDAgTVhQDQpGZWNoYTogMDUvMDgvMjAyNg0KSG9yYTogMDg6MzcgaHJzDQpSZWZlcmVuY2lhOiA2Mzg1NTI5DQoNCsK_Tm8gcmVjb25vY2VzIGVzdGEgb3BlcmFjacOzbj8gQ29tdW7DrWNhdGUgZGUgaW5tZWRpYXRvIGEgU3VwZXJMw61uZWENCjU1IDUxNjkgNDMwMy4NCg0KUGFyYSBtYXlvciBpbmZvcm1hY2nDs24gc29icmUgbG9zIHJlcXVpc2l0b3MsIGNvbWlzaW9uZXMgeSBjb25kaWNpb25lcyBkZSBjb250cmF0YWNpw7NuIGRlIGxvcyBwcm9kdWN0b3MgeSBzZXJ2aWNpb3MgZGUgU2FudGFuZGVyLCBhc8OtIGNvbW8gbnVlc3RybyBBdmlzbyBkZSBQcml2YWNpZGFkLCBjb25zdWx0YXIgd3d3LnNhbnRhbmRlci5jb20ubXg="
    }
}

# Outgoing transfer narrative email
OUTGOING_TRANSFER_PAYLOAD = {
    "mimeType": "text/plain",
    "body": {
        "data": "DQpfX19fX19fX19fX19fX19fX19fX19fX19fX19fX19fXw0KRnJvbTogQXZpc29zIFNhbnRhbmRlciA8bm90aWZpY2FjaW9uZXNAbm90aWZpY2FjaW9uZXMuc2FudGFuZGVyLmNvbS5teD4NClNlbnQ6IFdlZG5lc2RheSwgSnVseSA4LCAyMDI2IDAxOjM1IFBNDQpUbzogSkFORSBET0UgPEpBTkUuRE9FQEVYQU1QTEUuQ09NPg0KU3ViamVjdDogTm90aWZpY2FjacOzbiBUcmFuc2ZlcmVuY2lhIEludGVyYmFuY2FyaWEgYSB0cmF2w6lzIGRlIFN1cGVyTcOzdmlsLg0KDQpbY2lkOnZtcWVrZXdiZ2ZdDQoNCg0KQXByZWNpYWJsZSBKQU5FIERPRQ0KDQpMZSBpbmZvcm1hbW9zIHF1ZSByZWNpYmltb3Mgc3Ugc29saWNpdHVkIHBhcmEgcmVhbGl6YXIgdW5hIHRyYW5zZmVyZW5jaWEsIGRlIHN1IGN1ZW50YSB0ZXJtaW5hY2nDs24gNjQ2NiwgYSBsYSBjdWVudGEgdGVybWluYWNpw7NuIDAzNzYgZW4gSFNCQyBwb3IgdW4gaW1wb3J0ZSBkZSAkIDkwLjAwIGVsIDA4L0p1bC8yMDI2IGEgbGFzIDEzOjM1LCBjb24gbGEgcmVmZXJlbmNpYSA3OTQ4MTcwLg=="
    }
}

# Unique Points purchase email
UNIQUE_POINTS_PAYLOAD = {
    "mimeType": "text/plain",
    "body": {
        "data": "DQoNCl9fX19fX19fX19fX19fX19fX19fX19fX19fX19fX19fDQpGcm9tOiBTYW50YW5kZXIgPHNhbnRhbmRlckBlbnZpby5zYW50YW5kZXIuY29tLm14Pg0KU2VudDogTW9uZGF5LCBBdWd1c3QgMywgMjAyNiAwNTo0MSBQTQ0KVG86IEpBTkUuRE9FQEVYQU1QTEUuQ09NIDxKQU5FLkRPRUBFWEFNUExFLkNPTT4NClN1YmplY3Q6IFR1IGNvbXByYSB0ZSBhY2FiYSBkZSBnZW5lcmFyIFVuaXF1ZSBQb2ludHMNCg0KDQpTaSBubyBwdWVkZXMgdmVyIGVzdGUgbWVuc2FqZSBjb3JyZWN0YW1lbnRlIGhheiBjbGljIGFxdcOtPGh0dHBzOi8vY2xpY2suZW52aW8uc2FudGFuZGVyLmNvbS5teC8_cXM9RVhBTVBMRT4NCltodHRwczovL2ltYWdlLmVudmlvLnNhbnRhbmRlci5jb20ubXgvbGliL2ZlM2IxNTcwNzU2NDAwN2M3MjEyNzEvbS8xLzI1ODQ2MGRiLTUxOWQtNDUzZC1iNWY3LTBlYzYzODBjZTJkNi5qcGddDQoNCkhvbGEsIEVzdGltYWRvIENsaWVudGUuDQoNCjAzLzA4LzIwMjYuDQoNClJlYWxpemFzdGUgdW5hIGNvbXByYSBjb24gdHUgVGFyamV0YSBjcsOpZGl0byB0ZXJtaW5hY2nDs24gNTc4OA0KDQpbaHR0cHM6Ly9pbWFnZS5lbnZpby5zYW50YW5kZXIuY29tLm14L2xpYi9mZTNiMTU3MDc1NjQwMDdjNzIxMjcxL20vMS8xZGRkZGZkMy05YTVmLTRhZDctYTcxMy0yOTMzZWFlYjQxODMuanBnXQ0KDQpUZSBpbmZvcm1hbW9zIHF1ZSBzZSBhdXRvcml6w7MgdW5hIGNvbXByYQ0KZW4gV0wgKlNURUFNIFBVUkNIQVNFIHBvciB1biBtb250bw0KZGUgJDEsOTk5LjAwIE0uTi4="
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
        "data": "Cl9fX19fX19fX19fX19fX19fX19fX19fX19fX19fX19fCkZyb206IFNhbnRhbmRlciA8bm90aWZpY2FjaW9uQG9wZXJhY2lvbmVzLnNhbnRhbmRlci5jb20ubXg-ClNlbnQ6IFRodXJzZGF5LCBPY3RvYmVyIDEsIDIwMjYgMjo1Nzo1OCBQTSAoVVRDLTA2OjAwKSBHdWFkYWxhamFyYSwgTWV4aWNvIENpdHksIE1vbnRlcnJleQpUbzogamFuZS5kb2VAZXhhbXBsZS5jb20gPGphbmUuZG9lQGV4YW1wbGUuY29tPgpTdWJqZWN0OiBUdSBjb21wcmEgdGUgYWNhYmEgZGUgZ2VuZXJhciBVbmlxdWUgUG9pbnRzCgoKCltTYW50YW5kZXJdCjAxLzEwLzIwMjYKW1NhbnRhbmRlcl0KClJFQUxJWkFTVEUgVU5BIENPTVBSQSBDT04gVFUgVEFSSkVUQSBERSBjculkaXRvIFRFUk1JTkFDSdNOIDEzOTcKCkVzdGltYWRvIGNsaWVudGUsIHRlIGluZm9ybWFtb3MgcXVlIHNlIGF1dG9yaXrzIHVuYSBjb21wcmEgZW4gUkVTVEFVUkFUIENBTU9NSUxBIHBvciB1biBtb250byBkZSAkMjkxLjUwIE1YTi4KClBvciBlc3RhIHRyYW5zYWNjafNuIHNlIHN1bWFy4W4gYSBsYSBjdWVudGEgZGVsIHRpdHVsYXI6IDE3IFVuaXF1ZSBQb2ludCBxdWUgcG9kcuEgdXRpbGl6YXIgZW4gU2FudGFuZGVyIFVuaXF1ZSBSZXdhcmRzLgo="
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
