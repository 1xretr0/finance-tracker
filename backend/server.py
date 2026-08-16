# ---------------------------------------------------------------------------
# Flask API server & static file serving
# ---------------------------------------------------------------------------
import hmac
import hashlib
import os
import subprocess
import threading
import time
from collections import defaultdict, deque
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash

from backend.db.storage import (
    init_db,
    get_transactions,
    get_summary,
    get_monthly_totals,
    get_merchant_totals,
    get_breakdown,
    get_savings,
    get_uncategorized,
    update_categories,
    update_transaction,
    delete_transaction,
    get_categories,
    create_category,
    insert_transactions,
    get_user,
)
from backend.constants import (
    SERVER_PORT,
    API_TOKEN,
    GITHUB_WEBHOOK_SECRET,
    AUTH_MAX_FAILED_ATTEMPTS,
    AUTH_LOCKOUT_WINDOW_SECONDS,
    FLASK_DEBUG,
    TX_TYPES_SET,
    BANKS_SET,
    WSGI_PATH
)

app = Flask(__name__, static_folder=None)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
HTML_DIR = os.path.join(FRONTEND_DIR, "html")

# ---------------------------------------------------------------------------
# Auth: shared-secret bearer token on all /api/* routes.
# Page/static routes stay open — they serve static shells with no data.
# If API_TOKEN is unset, /api/* is rejected entirely (fail closed) so the
# server never accidentally runs open once it's reachable publicly.
#
# Failed attempts are throttled per source IP: once an IP racks up
# AUTH_MAX_FAILED_ATTEMPTS failures inside AUTH_LOCKOUT_WINDOW_SECONDS,
# further attempts get 429 without even checking the token, until old
# failures fall out of the window. In-memory only — fine for a
# single-process personal deployment; resets on restart.
# ---------------------------------------------------------------------------
_failed_attempts = defaultdict(deque)


def _is_locked_out(ip: str) -> bool:
    attempts = _failed_attempts[ip]
    cutoff = time.monotonic() - AUTH_LOCKOUT_WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    return len(attempts) >= AUTH_MAX_FAILED_ATTEMPTS


def _record_failed_attempt(ip: str) -> None:
    _failed_attempts[ip].append(time.monotonic())


@app.before_request
def require_api_token():
    if not request.path.startswith("/api/"):
        return None
    if not API_TOKEN:
        return jsonify({"error": "Server auth is not configured"}), 503

    ip = request.remote_addr or "unknown"
    if _is_locked_out(ip):
        return jsonify({"error": "Too many failed attempts, try again later"}), 429

    # /api/login is how a browser session obtains the bearer token in the
    # first place, so it can't require one — it's still covered by the
    # lockout check above and records its own failures below.
    if request.path == "/api/login":
        return None

    auth_header = request.headers.get("Authorization", "")
    if not hmac.compare_digest(auth_header, f"Bearer {API_TOKEN}"):
        _record_failed_attempt(ip)
        return jsonify({"error": "Unauthorized"}), 401
    return None

# ---------------------------------------------------------------------------
# Frontend page routes
# ---------------------------------------------------------------------------
@app.route("/login")
def login_page():
    return send_from_directory(HTML_DIR, "login.html")


@app.route("/")
def index():
    return send_from_directory(HTML_DIR, "index.html")


@app.route("/categorize")
def categorize_page():
    return send_from_directory(HTML_DIR, "categorize.html")


@app.route("/transactions")
def transactions_page():
    return send_from_directory(HTML_DIR, "transactions.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)

# ---------------------------------------------------------------------------
# API routes - Auth
# ---------------------------------------------------------------------------
@app.route("/api/login", methods=["POST"])
def api_login():
    if not API_TOKEN:
        return jsonify({"error": "Server auth is not configured"}), 503

    data = request.get_json()
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "Expected {username, password}"}), 400

    ip = request.remote_addr or "unknown"
    user = get_user(data["username"])
    if not user or not check_password_hash(user["password_hash"], data["password"]):
        _record_failed_attempt(ip)
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({"token": API_TOKEN, "username": user["username"]})

# ---------------------------------------------------------------------------
# API routes - Read operations
# ---------------------------------------------------------------------------


@app.route("/api/transactions")
def api_transactions():
    transactions = get_transactions(
        bank=request.args.get("bank"),
        tx_type=request.args.get("type"),
        start_date=request.args.get("start_date"),
        end_date=request.args.get("end_date"),
        person=request.args.get("person"),
    )
    return jsonify(transactions)


@app.route("/api/summary")
def api_summary():
    summary = get_summary(
        start_date=request.args.get("start_date"),
        end_date=request.args.get("end_date"),
    )
    return jsonify(summary)


@app.route("/api/monthly")
def api_monthly():
    data = get_monthly_totals(
        start_date=request.args.get("start_date"),
        end_date=request.args.get("end_date"),
    )
    return jsonify(data)


@app.route("/api/merchants")
def api_merchants():
    data = get_merchant_totals(
        start_date=request.args.get("start_date"),
        end_date=request.args.get("end_date"),
    )
    return jsonify(data)


@app.route("/api/breakdown")
def api_breakdown():
    month = request.args.get("month")
    if not month:
        month = datetime.now().strftime("%Y-%m")
    return jsonify(get_breakdown(month))


@app.route("/api/savings")
def api_savings():
    year = int(request.args.get("year", datetime.now().year))
    return jsonify(get_savings(year))


@app.route("/api/uncategorized")
def api_uncategorized():
    transactions = get_uncategorized()
    return jsonify(transactions)


@app.route("/api/transactions/categorize", methods=["PUT"])
def api_categorize():
    data = request.get_json()
    if not data or not isinstance(data, list):
        return jsonify({"error": "Expected a JSON array of {id, category}"}), 400
    updated = update_categories(data)
    return jsonify({"updated": updated})


@app.route("/api/transactions", methods=["POST"])
def api_create_transaction():
    data = request.get_json()
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object"}), 400

    required = ["type", "amount", "date", "bank"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    if not isinstance(data["amount"], (int, float)) or data["amount"] < 0:
        return jsonify({"error": "Amount must be a non-negative number"}), 400

    if data["type"] not in TX_TYPES_SET:
        return jsonify({"error": "Invalid transaction type"}), 400

    if data["bank"] not in BANKS_SET:
        return jsonify({"error": "Invalid bank"}), 400

    tx = {
        "bank": data['bank'],
        "type": data["type"],
        "amount": data["amount"],
        "currency": data.get("currency", "MXN"),
        "date": data["date"],
        "merchant": data.get("merchant"),
        "card_last4": data.get("card_last4"),
        "account_last4": data.get("account_last4"),
        "dest_account_last4": data.get("dest_account_last4"),
        "dest_bank": data.get("dest_bank"),
        "sender_bank": data.get("sender_bank"),
        "source_account": data.get("source_account"),
        "tracking_key": data.get("tracking_key"),
        "concept": data.get("concept"),
        "reference": data.get("reference"),
        "person": data.get("person"),
        "category": data.get("category"),
    }

    inserted = insert_transactions([tx])
    if inserted == 0:
        return jsonify({"error": "Duplicate transaction"}), 409
    return jsonify({"success": True}), 201


@app.route("/api/transactions/<int:tx_id>", methods=["PUT"])
def api_update_transaction(tx_id):
    data = request.get_json()
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object"}), 400
    if "amount" in data:
        if not isinstance(data["amount"], (int, float)) or data["amount"] < 0:
            return jsonify({"error": "Amount must be a non-negative number"}), 400
    success = update_transaction(tx_id, data)
    if not success:
        return jsonify({"error": "Transaction not found"}), 404
    return jsonify({"success": True})


@app.route("/api/transactions/<int:tx_id>", methods=["DELETE"])
def api_delete_transaction(tx_id):
    success = delete_transaction(tx_id)
    if not success:
        return jsonify({"error": "Transaction not found"}), 404
    return jsonify({"success": True})


@app.route("/api/categories")
def api_categories():
    return jsonify(get_categories())

# ---------------------------------------------------------------------------
# API routes - Write operations
# ---------------------------------------------------------------------------
@app.route("/api/categories", methods=["POST"])
def api_create_category():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Expected {name}"}), 400
    name = create_category(data["name"].strip())
    return jsonify({"name": name}), 201

# ---------------------------------------------------------------------------
# Github webhook setup
# ---------------------------------------------------------------------------
def verify_signature(payload, signature_header, secret):
    """Verifies that the webhook payload came from GitHub."""
    if not signature_header:
        return False

    # Header comes in as 'sha256=<hash>'
    sha_type, signature = signature_header.split('=')
    if sha_type != 'sha256':
        return False

    mac = hmac.new(secret.encode('utf-8'), msg=payload, digestmod=hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)

def trigger_reload():
    """Waits for the HTTP response to be sent to GitHub, then reloads WSGI."""
    time.sleep(1)

    # Touching the WSGI file reloads PythonAnywhere web apps automatically
    if os.path.exists(WSGI_PATH):
        os.utime(WSGI_PATH, None)

@app.route('/update_server', methods=['POST'])
def webhook():
    # 1. Verify HMAC Signature
    signature = request.headers.get('X-Hub-Signature-256')
    if not verify_signature(request.data, signature, GITHUB_WEBHOOK_SECRET):
        return jsonify({"error": "Invalid signature"}), 403

    # 2. Only respond to push events
    event = request.headers.get('X-GitHub-Event', 'ping')
    if event == 'ping':
        return jsonify({"message": "Ping received successfully"}), 200
    if event != 'push':
        return jsonify({"message": f"Event {event} ignored"}), 200

    # 3. Pull latest code and trigger asynchronous reload
    try:
        repo_dir = "/home/retr0py/finance-tracker"
        pull_output = subprocess.check_output(
            ["git", "pull", "origin", "main"],
            cwd=repo_dir,
            stderr=subprocess.STDOUT,
            text=True
        )

        threading.Thread(target=trigger_reload).start()

        return jsonify({
            "status": "success",
            "message": "Git pull successful. Server reload scheduled.",
            "output": pull_output
        }), 200

    except subprocess.CalledProcessError as e:
        return jsonify({
            "status": "error",
            "message": "Git pull failed",
            "details": e.output
        }), 500

# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=FLASK_DEBUG, port=SERVER_PORT)
