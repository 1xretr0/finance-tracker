from backend.banks.santander import parse_transaction


PURCHASE_EMAIL = """\
Te informamos que se autoriz=F3 una compra con tu tarjeta de cr=E9dito term=
inaci=F3n: 8949.

Monto:
$618.20 MXN

Comercio:
VIPS LEGARIA

Fecha y hora:
15/06/2026 15:01:07 hrs
"""

PURCHASE_NARRATIVE_EMAIL = """\
Estimado Cliente:

Te informamos que se ha realizado
una compra en el comercio UBR* PENDING.UBER.COM
con tu tarjeta de TDC
terminaci=F3n **8949, por
un monto de $74.63 MXN.

El 18/06/2026
a las 23:27:57 hrs.

Atentamente
Santander M=E9xico
"""


TRANSFER_EMAIL = """\
ABONO v=EDa SPEI

estimado cliente, recibiste v=EDa SPEI un abono por $96,863.53 MXN a tu cue=
nta terminaci=F3n 1234

Datos de la operaci=F3n

Fecha: 12/06/2026
Hora: 12:03 hrs
Banco emisor: HSBC
Cuenta origen:5678
Clave de rastreo: HSBC628982
Concepto de pago:NOMINAQ1126
"""

OUTGOING_TRANSFER_EMAIL = """\
Notificaci=F3n Transferencia Interbancaria a trav=E9s de SuperM=F3vil.

Apreciable JUAN PEREZ GARCIA

Le informamos que recibimos su solicitud para realizar una transferencia, d=
e su cuenta terminaci=F3n 1234, a la cuenta terminaci=F3n 9066 en BBVA MEXI=
CO por un importe de $ 505.00 el 24/Mar/2025 a las 09:41, con la referencia=
 7155691.
"""


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


IGNORED_OUTGOING_TRANSFER_EMAIL = """\
Notificaci=F3n Transferencia Interbancaria a trav=E9s de SuperM=F3vil.

Apreciable JUAN PEREZ GARCIA

Le informamos que recibimos su solicitud para realizar una transferencia, d=
e su cuenta terminaci=F3n 1234, a la cuenta terminaci=F3n 6184 en Mercado P=
ago W por un importe de $ 12000.00 el 16/Jun/2026 a las 22:59, con la refer=
encia 4392728.
"""


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
