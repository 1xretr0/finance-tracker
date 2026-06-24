import os
from flask import Flask, jsonify, request, send_from_directory
from backend.db.storage import (
    init_db,
    get_transactions,
    get_summary,
    get_uncategorized,
    update_categories,
    update_transaction,
    delete_transaction,
    get_categories,
    create_category,
)
from backend.constants import (
    TX_TYPE_PURCHASE,
    TX_TYPE_TRANSFER,
    TX_TYPE_OUTGOING_TRANSFER,
    DEFAULT_CATEGORY,
    SERVER_PORT,
)

app = Flask(__name__, static_folder=None)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
HTML_DIR = os.path.join(FRONTEND_DIR, "html")


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
    from backend.db.storage import get_connection

    conn = get_connection()
    query = """
        SELECT SUBSTR(date, 1, 7) as month, type, SUM(amount) as total, COUNT(*) as count
        FROM transactions WHERE 1=1
    """
    params = []
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " GROUP BY month, type ORDER BY month"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route("/api/merchants")
def api_merchants():
    from backend.db.storage import get_connection

    conn = get_connection()
    query = """
        SELECT merchant, SUM(amount) as total, COUNT(*) as count
        FROM transactions
        WHERE type = ? AND merchant IS NOT NULL
    """
    params = [TX_TYPE_PURCHASE]
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " GROUP BY merchant ORDER BY total DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route("/api/breakdown")
def api_breakdown():
    from backend.db.storage import get_connection

    month = request.args.get("month")
    if not month:
        from datetime import datetime

        month = datetime.now().strftime("%Y-%m")

    conn = get_connection()
    income_rows = conn.execute(
        """
        SELECT COALESCE(UPPER(category), ?) as category, SUM(amount) as total
        FROM transactions
        WHERE type = ? AND SUBSTR(date, 1, 7) = ?
        GROUP BY COALESCE(UPPER(category), ?) ORDER BY total DESC
    """,
        (DEFAULT_CATEGORY, TX_TYPE_TRANSFER, month, DEFAULT_CATEGORY),
    ).fetchall()

    expense_rows = conn.execute(
        """
        SELECT COALESCE(UPPER(category), ?) as category, SUM(amount) as total
        FROM transactions
        WHERE type IN (?, ?) AND SUBSTR(date, 1, 7) = ?
        GROUP BY COALESCE(UPPER(category), ?) ORDER BY total DESC
    """,
        (
            DEFAULT_CATEGORY,
            TX_TYPE_PURCHASE,
            TX_TYPE_OUTGOING_TRANSFER,
            month,
            DEFAULT_CATEGORY,
        ),
    ).fetchall()
    conn.close()

    return jsonify(
        {
            "income": [dict(r) for r in income_rows],
            "expenses": [dict(r) for r in expense_rows],
        }
    )


@app.route("/api/savings")
def api_savings():
    from datetime import datetime
    from backend.db.storage import get_connection

    year = request.args.get("year", datetime.now().year)
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT SUBSTR(date, 1, 7) as month,
               SUM(CASE WHEN type = ? THEN amount ELSE 0 END) as income,
               SUM(CASE WHEN type = ? THEN amount ELSE 0 END) as purchases,
               SUM(CASE WHEN type = ? THEN amount ELSE 0 END) as outgoing
        FROM transactions
        WHERE date >= ? AND date < ?
        GROUP BY month
        ORDER BY month
    """,
        (
            TX_TYPE_TRANSFER,
            TX_TYPE_PURCHASE,
            TX_TYPE_OUTGOING_TRANSFER,
            f"{year}-01-01",
            f"{int(year) + 1}-01-01",
        ),
    ).fetchall()
    conn.close()

    result = []
    for row in rows:
        r = dict(row)
        r["savings"] = r["income"] - r["purchases"] - r["outgoing"]
        result.append(r)
    return jsonify(result)


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
    from datetime import datetime, timezone
    from backend.db.storage import insert_transactions

    data = request.get_json()
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object"}), 400

    required = ["type", "amount", "date"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    if not isinstance(data["amount"], (int, float)) or data["amount"] < 0:
        return jsonify({"error": "Amount must be a non-negative number"}), 400

    if data["type"] not in (TX_TYPE_PURCHASE, TX_TYPE_TRANSFER, TX_TYPE_OUTGOING_TRANSFER):
        return jsonify({"error": "Invalid transaction type"}), 400

    tx = {
        "bank": data.get("bank", "manual"),
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


@app.route("/api/categories", methods=["POST"])
def api_create_category():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Expected {name}"}), 400
    name = create_category(data["name"].strip())
    return jsonify({"name": name}), 201


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=SERVER_PORT)
