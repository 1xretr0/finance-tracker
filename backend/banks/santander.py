import logging
import os
import re
import base64
import quopri
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from backend.constants import (
    BANK_SANTANDER,
    CURRENCY_MXN,
    TX_TYPE_PURCHASE,
    TX_TYPE_TRANSFER,
    TX_TYPE_OUTGOING_TRANSFER,
    GMAIL_SCOPES,
    GMAIL_SERVICE_NAME,
    GMAIL_SERVICE_VERSION,
    GMAIL_USER_ID,
    GMAIL_MAX_RESULTS,
    GMAIL_LABEL_SANTANDER,
    TOKEN_FILE,
    CREDENTIALS_FILE,
    SANTANDER_LAST_RUN_FILE,
    DATE_FORMAT_TX,
    MONTHS_ES,
    IGNORED_ACCOUNT_TRANSFERS,
)

logger = logging.getLogger(__name__)

def fetch_transactions() -> list[dict]:
    """Fetches Santander purchase notifications from Gmail and returns parsed transactions."""
    service = build(
        GMAIL_SERVICE_NAME, GMAIL_SERVICE_VERSION, credentials=_authenticate()
    )

    query = f"label:{GMAIL_LABEL_SANTANDER}"
    last_run = _get_last_run_date()
    if last_run:
        query += f" after:{last_run}"

    results = (
        service.users()
        .messages()
        .list(userId=GMAIL_USER_ID, q=query, maxResults=GMAIL_MAX_RESULTS)
        .execute()
    )

    messages = results.get("messages", [])
    transactions = []

    if not messages:
        logger.warning("No new Santander notifications found.")
        return transactions

    for msg_ref in messages:
        msg = (
            service.users()
            .messages()
            .get(userId=GMAIL_USER_ID, id=msg_ref["id"], format="full")
            .execute()
        )

        plain_body = _extract_plain_body(msg["payload"])
        if not plain_body:
            continue

        tx = parse_transaction(plain_body)
        if tx:
            transactions.append(tx)
            label = (
                tx.get("merchant")
                or tx.get("dest_bank")
                or tx.get("sender_bank")
                or tx["type"]
            )
            logger.info(f"  ✓ {tx['date']} | ${tx['amount']:.2f} | {label} ({tx['type']})")
        else:
            subject = _get_header(msg["payload"], "Subject")
            logger.warning(f"  ⚠ Could not parse transaction from: {subject}")

    return transactions


def _get_last_run_date() -> str | None:
    if os.path.exists(SANTANDER_LAST_RUN_FILE):
        with open(SANTANDER_LAST_RUN_FILE) as f:
            date = f.read().strip()
            logger.info(f"Last run date: {date}")
            return date
    
    logger.warning("No last run date file found!")
    return None


def save_last_run_date():
    from zoneinfo import ZoneInfo

    epoch = int(datetime.now(ZoneInfo("America/Mexico_City")).timestamp())
    with open(SANTANDER_LAST_RUN_FILE, "w") as f:
        f.write(str(epoch))
    
    logger.info("Last run date saved!")


def _authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def parse_transaction(plain_text: str) -> dict | None:
    """Parses a Santander notification plain text body into transaction data."""
    raw = quopri.decodestring(plain_text.encode("utf-8", errors="ignore"))
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        decoded = raw.decode("latin-1")

    if "ABONO" in decoded.upper() and "SPEI" in decoded.upper():
        return _parse_incoming_transfer(decoded)
    if "transferencia interbancaria" in decoded.lower():
        return _parse_outgoing_transfer(decoded)
    if "una compra en el comercio" in decoded.lower():
        return _parse_purchase_narrative(decoded)
    return _parse_purchase(decoded)


def _parse_purchase(decoded: str) -> dict | None:
    card_match = re.search(r"terminaci[oó]n:\s*(\d{4})", decoded)
    amount_match = re.search(r"Monto:\s*\$([0-9,]+\.\d{2})\s*(MXN)?", decoded)
    merchant_match = re.search(r"Comercio:\s*(.+)", decoded)
    date_match = re.search(
        r"Fecha y hora:\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})", decoded
    )

    if not amount_match or not merchant_match or not date_match:
        return None

    amount_str = amount_match.group(1).replace(",", "")
    date_str = f"{date_match.group(1)} {date_match.group(2)}"
    tx_date = datetime.strptime(date_str, DATE_FORMAT_TX)

    return {
        "bank": BANK_SANTANDER,
        "card_last4": card_match.group(1) if card_match else None,
        "amount": float(amount_str),
        "currency": CURRENCY_MXN,
        "merchant": merchant_match.group(1).strip(),
        "date": tx_date.isoformat(),
        "type": TX_TYPE_PURCHASE,
    }


def _parse_purchase_narrative(decoded: str) -> dict | None:
    """Parses the 'Pago/Compra con Tarjeta' narrative-style notification."""
    merchant_match = re.search(r"una compra en el comercio\s+(.+)", decoded, re.IGNORECASE)
    card_match = re.search(r"terminaci[oó]n\s*\*{0,2}(\d{4})", decoded)
    amount_match = re.search(r"un monto de\s*\$([0-9,]+\.\d{2})\s*(MXN)?", decoded)
    date_match = re.search(r"El\s+(\d{2}/\d{2}/\d{4})", decoded)
    time_match = re.search(r"a las\s+(\d{2}:\d{2}:\d{2})\s*hrs", decoded)

    if not amount_match or not merchant_match or not date_match:
        return None

    amount_str = amount_match.group(1).replace(",", "")
    time_str = time_match.group(1) if time_match else "00:00:00"
    date_str = f"{date_match.group(1)} {time_str}"
    tx_date = datetime.strptime(date_str, DATE_FORMAT_TX)

    return {
        "bank": BANK_SANTANDER,
        "card_last4": card_match.group(1) if card_match else None,
        "amount": float(amount_str),
        "currency": CURRENCY_MXN,
        "merchant": merchant_match.group(1).strip(),
        "date": tx_date.isoformat(),
        "type": TX_TYPE_PURCHASE,
    }


def _parse_incoming_transfer(decoded: str) -> dict | None:
    """
    :param decoded: decoded email content of the transaction
    :return: the dict of the parsed transfer transaction
    """
    account_match = re.search(r"cuenta terminaci[oó]n\s*(\d{4})", decoded)
    amount_match = re.search(r"\$([0-9,]+\.\d{2})\s*(MXN)?", decoded)
    date_match = re.search(r"Fecha:\s*(\d{2}/\d{2}/\d{4})", decoded)
    time_match = re.search(r"Hora:\s*(\d{2}:\d{2})\s*hrs", decoded)
    sender_bank_match = re.search(r"Banco emisor:\s*(.+)", decoded)
    source_account_match = re.search(r"Cuenta origen:\s*(\w+)", decoded)
    tracking_key_match = re.search(r"Clave de rastreo:\s*(\S+)", decoded)
    concept_match = re.search(r"Concepto de pago:\s*(.+)", decoded)

    if not amount_match or not date_match:
        return None
    
    if _is_internal_transfer(source_account_match, sender_bank_match):
        return None

    amount_str = amount_match.group(1).replace(",", "")
    time_str = time_match.group(1) + ":00" if time_match else "00:00:00"
    date_str = f"{date_match.group(1)} {time_str}"
    tx_date = datetime.strptime(date_str, DATE_FORMAT_TX)

    return {
        "bank": BANK_SANTANDER,
        "account_last4": account_match.group(1) if account_match else None,
        "amount": float(amount_str),
        "currency": CURRENCY_MXN,
        "sender_bank": sender_bank_match.group(1).strip() if sender_bank_match else None,
        "source_account": source_account_match.group(1) if source_account_match else None,
        "tracking_key": tracking_key_match.group(1).strip() if tracking_key_match else None,
        "concept": concept_match.group(1).strip() if concept_match else None,
        "date": tx_date.isoformat(),
        "type": TX_TYPE_TRANSFER,
    }


def _parse_outgoing_transfer(decoded: str) -> dict | None:
    source_match = re.search(r"de su cuenta.+?(\d{4}),", decoded)
    destination_account_digits = re.search(r"a la cuenta.+?(\d{4})", decoded)
    destination_bank_name = re.search(r"a la cuenta.+?\d{4}\s+en\s+(.+?)\s*por", decoded)
    amount_match = re.search(r"importe de\s*\$\s*([0-9,]+\.\d{2})", decoded)
    date_match = re.search(r"el\s+(\d{1,2}/\w{3}/\d{4})", decoded)
    time_match = re.search(r"a las\s+(\d{2}:\d{2})", decoded)
    reference_match = re.search(r"referencia\s+(\d+)", decoded)

    if not amount_match or not date_match:
        return None

    if _is_internal_transfer(destination_account_digits, destination_bank_name):
        return None

    amount_str = amount_match.group(1).replace(",", "")

    raw_date = date_match.group(1)
    day, month_str, year = raw_date.split("/")
    month = MONTHS_ES.get(month_str.lower(), "01")
    time_str = time_match.group(1) + ":00" if time_match else "00:00:00"
    tx_date = datetime.strptime(f"{day}/{month}/{year} {time_str}", DATE_FORMAT_TX)

    return {
        "bank": BANK_SANTANDER,
        "account_last4": source_match.group(1) if source_match else None,
        "dest_account_last4": destination_account_digits.group(1) if destination_account_digits else None,
        "dest_bank": destination_bank_name.group(1).strip() if destination_bank_name else None,
        "amount": float(amount_str),
        "currency": CURRENCY_MXN,
        "reference": reference_match.group(1) if reference_match else None,
        "date": tx_date.isoformat(),
        "type": TX_TYPE_OUTGOING_TRANSFER,
    }


def _is_internal_transfer(destination_account_digits, destination_bank_name) -> bool:
    if not destination_account_digits or not destination_bank_name:
        return False

    account = destination_account_digits.group(1)
    bank = destination_bank_name.group(1).strip().lower()

    is_ignored = any(
        account == rule["account_last4"] and bank == rule["bank"].lower()
        for rule in IGNORED_ACCOUNT_TRANSFERS
    )
    if is_ignored:
        logger.info(f"Ignoring internal transfer to account {account} at {bank}")
    return is_ignored


def _extract_plain_body(payload: dict) -> str | None:
    """Extracts the text/plain body from a Gmail message payload."""
    parts = [payload]
    while parts:
        part = parts.pop(0)
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("latin-1", errors="ignore")
        parts.extend(part.get("parts", []))
    return None


def _get_header(payload: dict, name: str) -> str:
    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
    return headers.get(name, "")
