import os

# Bank names
BANK_SANTANDER = "santander"

# Transaction types
TX_TYPE_PURCHASE = "purchase"
TX_TYPE_TRANSFER = "transfer"
TX_TYPE_OUTGOING_TRANSFER = "outgoing_transfer"

# Currency
CURRENCY_MXN = "MXN"

# Default category
DEFAULT_CATEGORY = "NO CATEGORY"

# Gmail API
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_SERVICE_NAME = "gmail"
GMAIL_SERVICE_VERSION = "v1"
GMAIL_USER_ID = "me"
GMAIL_MAX_RESULTS = 250
GMAIL_LABEL_SANTANDER = "santander_notifications"

# File paths
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(_PROJECT_ROOT, "token.json")
CREDENTIALS_FILE = os.path.join(_PROJECT_ROOT, "credentials.json")
SANTANDER_LAST_RUN_FILE = os.path.join(
    os.path.dirname(__file__), "banks", "santander_last_run.txt"
)
DB_FILENAME = "finance_tracker.db"
DB_PATH = os.path.join(os.path.dirname(__file__), "db", DB_FILENAME)

# Date formats
DATE_FORMAT_TX = "%d/%m/%Y %H:%M:%S"

# Server
SERVER_PORT = 5000

# Spanish month abbreviations
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

IGNORED_ACCOUNT_TRANSFERS = [
    {"account_last4": "6184", "bank": "Mercado Pago W"},
    {"account_last4": "8275", "bank": "STP"},
]
