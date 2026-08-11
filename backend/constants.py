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
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "db", DB_FILENAME)
DB_PATH = os.environ.get("DB_PATH", _DEFAULT_DB_PATH)

# ---------------------------------------------------------------------------
# Hosting / remote API configuration
# ---------------------------------------------------------------------------
# API_TOKEN: shared secret required on every /api/* request once the server is
# publicly hosted. Unset locally by default (auth is disabled for local dev).
API_TOKEN = os.environ.get("API_TOKEN")

# REMOTE_API_URL: when set on the machine running process_transactions, newly
# fetched transactions are pushed to this hosted API instead of being written
# to a local DB directly.
REMOTE_API_URL = os.environ.get("REMOTE_API_URL")

# FLASK_DEBUG: enables Flask's reloader and interactive debugger. Must stay
# off whenever the server is reachable over the network — the interactive
# debugger allows arbitrary code execution if an unhandled exception exposes
# it. Off by default; opt in explicitly for local development.
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

# Auth rate limiting: after this many failed /api/* auth attempts from the
# same IP within the window, further attempts are rejected with 429 until
# the window elapses. Slows down token brute-forcing/guessing.
AUTH_MAX_FAILED_ATTEMPTS = 10
AUTH_LOCKOUT_WINDOW_SECONDS = 300

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
PATTERN_OUTGOING_TRANSFER_NARRATIVE = "le informamos que recibimos su solicitud para realizar una transferencia"
PATTERN_OUTGOING_TRANSFER_CONFIRMATION = "confirmación de transferencia"
PATTERN_PURCHASE_NARRATIVE = "una compra en el comercio"
PATTERN_UNIQUE_POINTS_PURCHASE_AMOUNT = "por un monto"
PATTERN_UNIQUE_POINTS_PURCHASE_CURRENCY = "m.n."

# Common regex components
PATTERN_ACCOUNT_TERMINATION = r"terminaci[oó]n"
