import os

# ---------------------------------------------------------------------------
# Bank identifiers
# ---------------------------------------------------------------------------
BANK_SANTANDER = "santander"

# ---------------------------------------------------------------------------
# Transaction types
# ---------------------------------------------------------------------------
TX_TYPE_PURCHASE = "purchase"
TX_TYPE_TRANSFER = "transfer"
TX_TYPE_OUTGOING_TRANSFER = "outgoing_transfer"

# ---------------------------------------------------------------------------
# Currency & categories
# ---------------------------------------------------------------------------
CURRENCY_MXN = "MXN"
DEFAULT_CATEGORY = "NO CATEGORY"

# ---------------------------------------------------------------------------
# Gmail API configuration
# ---------------------------------------------------------------------------
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_SERVICE_NAME = "gmail"
GMAIL_SERVICE_VERSION = "v1"
GMAIL_USER_ID = "me"
GMAIL_MAX_RESULTS = 250
GMAIL_LABEL_SANTANDER = "santander_notifications"

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(_PROJECT_ROOT, "token.json")
CREDENTIALS_FILE = os.path.join(_PROJECT_ROOT, "credentials.json")
SANTANDER_LAST_RUN_FILE = os.path.join(
    os.path.dirname(__file__), "banks", "santander_last_run.txt"
)
DB_FILENAME = "finance_tracker.db"
DB_PATH = os.path.join(os.path.dirname(__file__), "db", DB_FILENAME)

# ---------------------------------------------------------------------------
# Date & time formats
# ---------------------------------------------------------------------------
DATE_FORMAT_TX = "%d/%m/%Y %H:%M:%S"
DEFAULT_TIME = "00:00:00"

MONTHS_ES = {
    "ene": "01",
    "feb": "02",
    "mar": "03",
    "abr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "ago": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dic": "12",
}

# ---------------------------------------------------------------------------
# Server configuration
# ---------------------------------------------------------------------------
SERVER_PORT = 5000

# ---------------------------------------------------------------------------
# Transaction processing rules
# ---------------------------------------------------------------------------
UPDATABLE_FIELDS = {"amount", "merchant", "category"}

IGNORED_ACCOUNT_TRANSFERS = [
    {"account_last4": "6184", "bank": "Mercado Pago W"},
    {"account_last4": "8275", "bank": "STP"},
]

# ---------------------------------------------------------------------------
# Santander email parsing patterns
# ---------------------------------------------------------------------------
# Dispatch guard signatures (case-insensitive)
PATTERN_INCOMING_TRANSFER_UPPER = "spei un abono por"
PATTERN_INCOMING_TRANSFER_SPEI = "spei"
PATTERN_OUTGOING_TRANSFER_NARRATIVE = "transferencia interbancaria"
PATTERN_OUTGOING_TRANSFER_CONFIRMATION = "de transferencia"
PATTERN_OUTGOING_TRANSFER_CONFIRMATION_DETAILS = "estimado cliente, realizaste una transferencia de tu cuenta"
PATTERN_PURCHASE_SUBJECT = 'pago/compra con Tarjeta Santander'
PATTERN_PURCHASE_NARRATIVE = "una compra en el comercio"
PATTERN_UNIQUE_POINTS_PURCHASE_AMOUNT = "por un monto"
PATTERN_UNIQUE_POINTS_PURCHASE_CURRENCY = "m.n."

# Common regex components
PATTERN_ACCOUNT_TERMINATION = r"terminaci[oó]n"
