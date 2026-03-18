import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
PORT = int(os.getenv("PORT", 3000))

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing BOT_TOKEN or CHAT_ID in .env file")

app = Flask(__name__)
CORS(app)


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()


# ── POST /order  — called when customer clicks "CONTINUE TO PAYMENT" ──────────
@app.route("/order", methods=["POST"])
def receive_order():
    data = request.get_json(force=True)

    full_name    = data.get("fullName", "")
    email        = data.get("email", "N/A")
    phone        = data.get("phone", "")
    location     = data.get("locationLink", "")
    currency     = data.get("currency", "USD")
    items        = data.get("items", [])
    total        = data.get("total", "0")

    if not full_name or not phone or not items:
        return jsonify(ok=False, error="Missing required fields"), 400

    symbol = "៛" if currency == "KHR" else "$"

    item_lines = "\n".join(
        f"  • {i.get('name')} | {i.get('color')} · {i.get('size')} · x{i.get('qty')} — {symbol}{i.get('price')}"
        for i in items
    )

    location_text = f"[View on Map]({location})" if location else "N/A"

    message = (
        f"🛍️ *NEW ORDER RECEIVED*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Name:* {full_name}\n"
        f"📧 *Email:* {email}\n"
        f"📞 *Phone:* {phone}\n"
        f"📍 *Location:* {location_text}\n"
        f"💱 *Currency:* {currency}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 *Order Items:*\n{item_lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Total: {symbol}{total}*\n"
        f"⏳ *Status: Awaiting Payment*"
    )

    try:
        send_telegram(message)
        return jsonify(ok=True)
    except Exception as e:
        print(f"Telegram error: {e}")
        return jsonify(ok=False, error="Failed to send Telegram message"), 500


# ── POST /payment  — called when customer submits transaction reference ────────
@app.route("/payment", methods=["POST"])
def receive_payment():
    data = request.get_json(force=True)

    full_name       = data.get("fullName", "")
    phone           = data.get("phone", "")
    transaction_ref = data.get("transactionRef", "")
    currency        = data.get("currency", "USD")
    total           = data.get("total", "0")

    if not transaction_ref:
        return jsonify(ok=False, error="Missing transactionRef"), 400

    symbol = "៛" if currency == "KHR" else "$"

    message = (
        f"✅ *PAYMENT SUBMITTED*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Name:* {full_name}\n"
        f"📞 *Phone:* {phone}\n"
        f"💰 *Amount: {symbol}{total}*\n"
        f"🔖 *Transaction Ref:* `{transaction_ref}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Please verify in ABA and confirm the order."
    )

    try:
        send_telegram(message)
        return jsonify(ok=True)
    except Exception as e:
        print(f"Telegram error: {e}")
        return jsonify(ok=False, error="Failed to send Telegram message"), 500


# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return "Luxe Wear Order Bot is running ✅"


if __name__ == "__main__":
    print(f"✅ Server running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
