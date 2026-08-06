# ---------------------------------------------------------------------------
# Tests for Santander email parsers
# ---------------------------------------------------------------------------
from backend.banks.santander import parse_transaction

# ---------------------------------------------------------------------------
# Test data: Purchase emails (field-style)
# ---------------------------------------------------------------------------
PURCHASE_EMAIL = """\
Te informamos que se autorizó una compra con tu tarjeta de crédito terminación: 8949.

Monto:
$618.20 MXN

Comercio:
VIPS LEGARIA

Fecha y hora:
15/06/2026 15:01:07 hrs
"""

# ---------------------------------------------------------------------------
# Test data: Purchase emails (narrative-style)
# ---------------------------------------------------------------------------
PURCHASE_NARRATIVE_EMAIL = """\
Estimado Cliente:

Te informamos que se ha realizado
una compra en el comercio UBR* PENDING.UBER.COM
con tu tarjeta de TDC
terminación **8949, por
un monto de $74.63 MXN.

El 18/06/2026
a las 23:27:57 hrs.

Atentamente
Santander México
"""

# ---------------------------------------------------------------------------
# Test suite: Purchase parser (field-style)
# ---------------------------------------------------------------------------
class TestPurchaseParser:
    def test_parses_amount(self):
        tx = parse_transaction(PURCHASE_EMAIL)
        assert tx["amount"] == 618.20

    def test_parses_merchant(self):
        tx = parse_transaction(PURCHASE_EMAIL)
        assert tx["merchant"] == "VIPS LEGARIA"

    def test_parses_card_last4(self):
        tx = parse_transaction(PURCHASE_EMAIL)
        assert tx["card_last4"] == "8949"

    def test_parses_date(self):
        tx = parse_transaction(PURCHASE_EMAIL)
        assert tx["date"] == "2026-06-15T15:01:07"

    def test_type_is_purchase(self):
        tx = parse_transaction(PURCHASE_EMAIL)
        assert tx["type"] == "purchase"

    def test_currency_is_mxn(self):
        tx = parse_transaction(PURCHASE_EMAIL)
        assert tx["currency"] == "MXN"

    def test_bank_is_santander(self):
        tx = parse_transaction(PURCHASE_EMAIL)
        assert tx["bank"] == "santander"

    def test_amount_with_thousands(self):
        email = PURCHASE_EMAIL.replace("$618.20", "$1,234.56")
        tx = parse_transaction(email)
        assert tx["amount"] == 1234.56

    def test_returns_none_for_unparseable(self):
        tx = parse_transaction("Hello this is not a bank email")
        assert tx is None

# ---------------------------------------------------------------------------
# Test suite: Purchase parser (narrative-style)
# ---------------------------------------------------------------------------
class TestPurchaseNarrativeParser:
    def test_parses_amount(self):
        tx = parse_transaction(PURCHASE_NARRATIVE_EMAIL)
        assert tx["amount"] == 74.63

    def test_parses_merchant(self):
        tx = parse_transaction(PURCHASE_NARRATIVE_EMAIL)
        assert tx["merchant"] == "UBR* PENDING.UBER.COM"

    def test_parses_card_last4(self):
        tx = parse_transaction(PURCHASE_NARRATIVE_EMAIL)
        assert tx["card_last4"] == "8949"

    def test_parses_date(self):
        tx = parse_transaction(PURCHASE_NARRATIVE_EMAIL)
        assert tx["date"] == "2026-06-18T23:27:57"

    def test_type_is_purchase(self):
        tx = parse_transaction(PURCHASE_NARRATIVE_EMAIL)
        assert tx["type"] == "purchase"

    def test_currency_is_mxn(self):
        tx = parse_transaction(PURCHASE_NARRATIVE_EMAIL)
        assert tx["currency"] == "MXN"

    def test_bank_is_santander(self):
        tx = parse_transaction(PURCHASE_NARRATIVE_EMAIL)
        assert tx["bank"] == "santander"

    def test_amount_with_thousands(self):
        email = PURCHASE_NARRATIVE_EMAIL.replace("$74.63", "$1,234.56")
        tx = parse_transaction(email)
        assert tx["amount"] == 1234.56

# ---------------------------------------------------------------------------
# Test data: Unique Points purchase emails
# ---------------------------------------------------------------------------
UNIQUE_POINTS_PURCHASE_EMAIL = """\
Hola, Estimado Cliente.

03/08/2026.

Realizaste una compra con tu Tarjeta crédito terminación 5788

Te informamos que se autorizó una compra
en WL *STEAM PURCHASE por un monto
de $1,999.00 M.N.

115
"""

# ---------------------------------------------------------------------------
# Test suite: Unique Points purchase parser
# ---------------------------------------------------------------------------
class TestUniquePointsPurchaseParser:
    def test_parses_amount(self):
        tx = parse_transaction(UNIQUE_POINTS_PURCHASE_EMAIL)
        assert tx["amount"] == 1999.00

    def test_parses_merchant(self):
        tx = parse_transaction(UNIQUE_POINTS_PURCHASE_EMAIL)
        assert tx["merchant"] == "WL *STEAM PURCHASE"

    def test_parses_card_last4(self):
        tx = parse_transaction(UNIQUE_POINTS_PURCHASE_EMAIL)
        assert tx["card_last4"] == "5788"

    def test_parses_date(self):
        tx = parse_transaction(UNIQUE_POINTS_PURCHASE_EMAIL)
        assert tx["date"] == "2026-08-03T00:00:00"

    def test_type_is_purchase(self):
        tx = parse_transaction(UNIQUE_POINTS_PURCHASE_EMAIL)
        assert tx["type"] == "purchase"

    def test_currency_is_mxn(self):
        tx = parse_transaction(UNIQUE_POINTS_PURCHASE_EMAIL)
        assert tx["currency"] == "MXN"

    def test_bank_is_santander(self):
        tx = parse_transaction(UNIQUE_POINTS_PURCHASE_EMAIL)
        assert tx["bank"] == "santander"

    def test_amount_with_thousands(self):
        email = UNIQUE_POINTS_PURCHASE_EMAIL.replace("$1,999.00", "$12,345.67")
        tx = parse_transaction(email)
        assert tx["amount"] == 12345.67

# ---------------------------------------------------------------------------
# Test data: Transfer emails (incoming)
# ---------------------------------------------------------------------------
TRANSFER_EMAIL = """\
ABONO vía SPEI

estimado cliente, recibiste vía SPEI un abono por $96,863.53 MXN a tu cuenta terminación 1234

Datos de la operación

Fecha: 12/06/2026
Hora: 12:03 hrs
Banco emisor: HSBC
Cuenta origen:5678
Clave de rastreo: HSBC628982
Concepto de pago:NOMINAQ1126
"""

# ---------------------------------------------------------------------------
# Test suite: Incoming transfer parser
# ---------------------------------------------------------------------------
class TestTransferParser:
    def test_parses_amount(self):
        tx = parse_transaction(TRANSFER_EMAIL)
        assert tx["amount"] == 96863.53

    def test_parses_account_last4(self):
        tx = parse_transaction(TRANSFER_EMAIL)
        assert tx["account_last4"] == "1234"

    def test_parses_sender_bank(self):
        tx = parse_transaction(TRANSFER_EMAIL)
        assert tx["sender_bank"] == "HSBC"

    def test_parses_source_account(self):
        tx = parse_transaction(TRANSFER_EMAIL)
        assert tx["source_account"] == "5678"

    def test_parses_tracking_key(self):
        tx = parse_transaction(TRANSFER_EMAIL)
        assert tx["tracking_key"] == "HSBC628982"

    def test_parses_concept(self):
        tx = parse_transaction(TRANSFER_EMAIL)
        assert tx["concept"] == "NOMINAQ1126"

    def test_parses_date(self):
        tx = parse_transaction(TRANSFER_EMAIL)
        assert tx["date"] == "2026-06-12T12:03:00"

    def test_type_is_transfer(self):
        tx = parse_transaction(TRANSFER_EMAIL)
        assert tx["type"] == "transfer"

    def test_bank_is_santander(self):
        tx = parse_transaction(TRANSFER_EMAIL)
        assert tx["bank"] == "santander"

# ---------------------------------------------------------------------------
# Test data: Transfer emails (outgoing - narrative style)
# ---------------------------------------------------------------------------
OUTGOING_TRANSFER_EMAIL = """\
Notificación Transferencia Interbancaria a través de SuperMóvil.

Apreciable JUAN PEREZ GARCIA

Le informamos que recibimos su solicitud para realizar una transferencia, de su cuenta terminación 1234, a la cuenta terminación 9066 en BBVA MEXICO por un importe de $ 505.00 el 24/Mar/2025 a las 09:41, con la referencia 7155691.
"""

# ---------------------------------------------------------------------------
# Test data: Outgoing transfers to ignored accounts
# ---------------------------------------------------------------------------
IGNORED_OUTGOING_TRANSFER_EMAIL = """\
Notificación Transferencia Interbancaria a través de SuperMóvil.

Apreciable JUAN PEREZ GARCIA

Le informamos que recibimos su solicitud para realizar una transferencia, de su cuenta terminación 1234, a la cuenta terminación 6184 en Mercado Pago W por un importe de $ 12000.00 el 16/Jun/2026 a las 22:59, con la referencia 4392728.
"""

# ---------------------------------------------------------------------------
# Test suite: Outgoing transfer parser (narrative-style)
# ---------------------------------------------------------------------------
class TestOutgoingTransferParser:
    def test_parses_amount(self):
        tx = parse_transaction(OUTGOING_TRANSFER_EMAIL)
        assert tx["amount"] == 505.00

    def test_parses_source_account(self):
        tx = parse_transaction(OUTGOING_TRANSFER_EMAIL)
        assert tx["account_last4"] == "1234"

    def test_parses_dest_account(self):
        tx = parse_transaction(OUTGOING_TRANSFER_EMAIL)
        assert tx["dest_account_last4"] == "9066"

    def test_parses_dest_bank(self):
        tx = parse_transaction(OUTGOING_TRANSFER_EMAIL)
        assert tx["dest_bank"] == "BBVA MEXICO"

    def test_parses_reference(self):
        tx = parse_transaction(OUTGOING_TRANSFER_EMAIL)
        assert tx["reference"] == "7155691"

    def test_parses_date(self):
        tx = parse_transaction(OUTGOING_TRANSFER_EMAIL)
        assert tx["date"] == "2025-03-24T09:41:00"

    def test_type_is_outgoing_transfer(self):
        tx = parse_transaction(OUTGOING_TRANSFER_EMAIL)
        assert tx["type"] == "outgoing_transfer"

    def test_bank_is_santander(self):
        tx = parse_transaction(OUTGOING_TRANSFER_EMAIL)
        assert tx["bank"] == "santander"

    def test_ignores_transfer_to_mercado_pago_w(self):
        tx = parse_transaction(IGNORED_OUTGOING_TRANSFER_EMAIL)
        assert tx is None

    def test_ignores_transfer_to_stp(self):
        email = """\
Notificación Transferencia Interbancaria a través de SuperMóvil.

Apreciable JUAN PEREZ GARCIA

Le informamos que recibimos su solicitud para realizar una transferencia, de su cuenta terminación 1234, a la cuenta terminación 8275 en STP por un importe de $ 1500.00 el 10/Jun/2026 a las 11:00, con la referencia 9999999.
"""
        tx = parse_transaction(email)
        assert tx is None

    def test_amount_with_thousands(self):
        email = OUTGOING_TRANSFER_EMAIL.replace("$ 505.00", "$ 12,500.00")
        tx = parse_transaction(email)
        assert tx["amount"] == 12500.00

# ---------------------------------------------------------------------------
# Test data: Incoming transfers from ignored accounts
# ---------------------------------------------------------------------------
IGNORED_INCOMING_TRANSFER_EMAIL = """\
ABONO vía SPEI

estimado cliente, recibiste vía SPEI un abono por $1,000.00 MXN a tu cuenta terminación 1234

Datos de la operación

Fecha: 15/06/2026
Hora: 10:00 hrs
Banco emisor: Mercado Pago W
Cuenta origen:6184
Clave de rastreo: MP123456
Concepto de pago:REEMBOLSO
"""

# ---------------------------------------------------------------------------
# Test suite: Incoming transfer ignore list
# ---------------------------------------------------------------------------
class TestIncomingTransferIgnoreList:
    def test_ignores_transfer_from_mercado_pago_w(self):
        tx = parse_transaction(IGNORED_INCOMING_TRANSFER_EMAIL)
        assert tx is None

    def test_does_not_ignore_unknown_sender(self):
        email = IGNORED_INCOMING_TRANSFER_EMAIL.replace(
            "Banco emisor: Mercado Pago W\nCuenta origen:6184",
            "Banco emisor: BANAMEX\nCuenta origen:9999",
        )
        tx = parse_transaction(email)
        assert tx is not None
        assert tx["type"] == "transfer"

# ---------------------------------------------------------------------------
# Test data: Outgoing transfer confirmation emails (field-style)
# ---------------------------------------------------------------------------
OUTGOING_TRANSFER_CONFIRMATION_EMAIL = """\
Confirmación de transferencia

Estimado cliente, realizaste una transferencia de tu cuenta terminación 6466 a la cuenta terminación 1306 en BBVA MEXICO.

Detalles de la operación

Importe: $4,669.00 MXP
Fecha: 05/08/2026
Hora: 08:37 hrs
Referencia: 6385529
"""

# ---------------------------------------------------------------------------
# Test suite: Outgoing transfer confirmation parser (field-style)
# ---------------------------------------------------------------------------
class TestOutgoingTransferConfirmationParser:
    def test_parses_amount(self):
        tx = parse_transaction(OUTGOING_TRANSFER_CONFIRMATION_EMAIL)
        assert tx["amount"] == 4669.00

    def test_parses_source_account(self):
        tx = parse_transaction(OUTGOING_TRANSFER_CONFIRMATION_EMAIL)
        assert tx["account_last4"] == "6466"

    def test_parses_dest_account(self):
        tx = parse_transaction(OUTGOING_TRANSFER_CONFIRMATION_EMAIL)
        assert tx["dest_account_last4"] == "1306"

    def test_parses_dest_bank(self):
        tx = parse_transaction(OUTGOING_TRANSFER_CONFIRMATION_EMAIL)
        assert tx["dest_bank"] == "BBVA MEXICO"

    def test_parses_reference(self):
        tx = parse_transaction(OUTGOING_TRANSFER_CONFIRMATION_EMAIL)
        assert tx["reference"] == "6385529"

    def test_parses_date(self):
        tx = parse_transaction(OUTGOING_TRANSFER_CONFIRMATION_EMAIL)
        assert tx["date"] == "2026-08-05T08:37:00"

    def test_type_is_outgoing_transfer(self):
        tx = parse_transaction(OUTGOING_TRANSFER_CONFIRMATION_EMAIL)
        assert tx["type"] == "outgoing_transfer"

    def test_bank_is_santander(self):
        tx = parse_transaction(OUTGOING_TRANSFER_CONFIRMATION_EMAIL)
        assert tx["bank"] == "santander"

    def test_currency_is_mxn(self):
        tx = parse_transaction(OUTGOING_TRANSFER_CONFIRMATION_EMAIL)
        assert tx["currency"] == "MXN"

    def test_amount_with_thousands(self):
        email = OUTGOING_TRANSFER_CONFIRMATION_EMAIL.replace("$4,669.00", "$12,345.67")
        tx = parse_transaction(email)
        assert tx["amount"] == 12345.67

    def test_ignores_transfer_to_mercado_pago_w(self):
        email = OUTGOING_TRANSFER_CONFIRMATION_EMAIL.replace(
            "terminación 1306 en BBVA MEXICO",
            "terminación 6184 en Mercado Pago W"
        )
        tx = parse_transaction(email)
        assert tx is None

    def test_ignores_transfer_to_stp(self):
        email = OUTGOING_TRANSFER_CONFIRMATION_EMAIL.replace(
            "terminación 1306 en BBVA MEXICO",
            "terminación 8275 en STP"
        )
        tx = parse_transaction(email)
        assert tx is None
