import os
import json
import datetime
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN        = os.getenv("BOT_TOKEN")
CHAT_ID          = os.getenv("CHAT_ID")
BREVO_API_KEY    = os.getenv("BREVO_API_KEY")
GMAIL_USER       = os.getenv("GMAIL_USER")
PORT             = int(os.getenv("PORT", 3000))

# ── Firebase Admin (for password reset) ────────────────────────────────────────
_fb_app = None
_fb_db  = None
def _get_firebase():
    global _fb_app, _fb_db
    if _fb_app:
        return _fb_app, _fb_db
    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT", "")
    if not sa_json:
        return None, None
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        cred    = credentials.Certificate(json.loads(sa_json))
        _fb_app = firebase_admin.initialize_app(cred)
        _fb_db  = firestore.client()
    except Exception as e:
        print("Firebase Admin init error:", e)
    return _fb_app, _fb_db

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing BOT_TOKEN or CHAT_ID in .env file")

app = Flask(__name__)
CORS(app)

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        res = app.make_response("")
        res.headers["Access-Control-Allow-Origin"]  = "*"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return res

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# ── Telegram ──────────────────────────────────────────────────────────────────
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


# ── Brevo ──────────────────────────────────────────────────────────────────────
def send_email(to_email: str, subject: str, html_body: str):
    resp = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "sender": {"name": "Luxe Wear", "email": GMAIL_USER},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html_body,
        },
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise Exception(f"Brevo error {resp.status_code}: {resp.text}")


# ── POST /send-code  — email verification during signup ───────────────────────
@app.route("/send-code", methods=["POST"])
def send_verification_code():
    data  = request.get_json(force=True)
    email = data.get("email", "")
    code  = data.get("code", "")
    name  = data.get("name", "Guest")

    if not email or not code:
        return jsonify(ok=False, error="Missing email or code"), 400

    if not BREVO_API_KEY:
        return jsonify(ok=False, error="Brevo not configured on server"), 500

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 0; }}
        .wrapper {{ max-width: 480px; margin: 40px auto; background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
        .header {{ background: #0a0a0a; padding: 36px 40px; text-align: center; }}
        .header h1 {{ color: #fff; font-size: 20px; font-weight: 600; letter-spacing: 0.15em; text-transform: uppercase; margin: 0; }}
        .body {{ padding: 40px; text-align: center; }}
        .greeting {{ font-size: 16px; color: #333; margin-bottom: 8px; }}
        .subtitle {{ font-size: 13px; color: #888; margin-bottom: 32px; }}
        .code-box {{ display: inline-block; background: #f8f8f8; border: 2px solid #e5e5e5; border-radius: 12px; padding: 20px 40px; margin-bottom: 28px; }}
        .code {{ font-size: 42px; font-weight: 700; letter-spacing: 0.25em; color: #0a0a0a; }}
        .note {{ font-size: 12px; color: #aaa; margin-bottom: 8px; }}
        .footer {{ background: #f8f8f8; padding: 24px 40px; text-align: center; font-size: 11px; color: #bbb; }}
      </style>
    </head>
    <body>
      <div class="wrapper">
        <div class="header"><h1>Luxe Wear</h1></div>
        <div class="body">
          <p class="greeting">Hi {name},</p>
          <p class="subtitle">Use the code below to verify your email and create your account.</p>
          <div class="code-box">
            <div class="code">{code}</div>
          </div>
          <p class="note">This code expires in <strong>10 minutes</strong>.</p>
          <p class="note">If you didn't request this, you can safely ignore this email.</p>
        </div>
        <div class="footer">© {os.getenv("YEAR", "2026")} Luxe Wear · All rights reserved</div>
      </div>
    </body>
    </html>
    """

    try:
        send_email(email, "Your Luxe Wear verification code", html)
        return jsonify(ok=True)
    except Exception as e:
        import traceback
        print(f"Email error: {e}")
        print(traceback.format_exc())
        return jsonify(ok=False, error=str(e)), 500


# ── POST /order  — called when customer clicks "CONTINUE TO PAYMENT" ──────────
@app.route("/order", methods=["POST"])
def receive_order():
    data = request.get_json(force=True)

    full_name = data.get("fullName", "")
    email     = data.get("email", "N/A")
    phone     = data.get("phone", "")
    location  = data.get("locationLink", "")
    currency  = data.get("currency", "USD")
    items     = data.get("items", [])
    total     = data.get("total", "0")

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


# ── POST /send-reset-code  — password reset email ─────────────────────────────
@app.route("/send-reset-code", methods=["POST"])
def send_reset_code():
    data  = request.get_json(force=True)
    email = data.get("email", "")
    code  = data.get("code", "")

    if not email or not code:
        return jsonify(ok=False, error="Missing email or code"), 400
    if not BREVO_API_KEY:
        return jsonify(ok=False, error="Brevo not configured"), 500

    html = f"""
    <!DOCTYPE html><html><head><meta charset="UTF-8">
    <style>
      body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background:#f4f4f4; margin:0; padding:0; }}
      .wrapper {{ max-width:480px; margin:40px auto; background:#fff; border-radius:16px; overflow:hidden; box-shadow:0 4px 24px rgba(0,0,0,.08); }}
      .header  {{ background:#0a0a0a; padding:36px 40px; text-align:center; }}
      .header h1 {{ color:#fff; font-size:20px; font-weight:600; letter-spacing:.15em; text-transform:uppercase; margin:0; }}
      .body    {{ padding:40px; text-align:center; }}
      .tag     {{ display:inline-block; background:#fff3cd; color:#856404; font-size:11px; font-weight:600; letter-spacing:.1em; text-transform:uppercase; padding:4px 12px; border-radius:20px; margin-bottom:20px; }}
      .subtitle {{ font-size:13px; color:#888; margin-bottom:32px; }}
      .code-box {{ display:inline-block; background:#f8f8f8; border:2px solid #e5e5e5; border-radius:12px; padding:20px 40px; margin-bottom:28px; }}
      .code    {{ font-size:42px; font-weight:700; letter-spacing:.25em; color:#0a0a0a; }}
      .note    {{ font-size:12px; color:#aaa; margin-bottom:8px; }}
      .footer  {{ background:#f8f8f8; padding:24px 40px; text-align:center; font-size:11px; color:#bbb; }}
    </style></head><body>
      <div class="wrapper">
        <div class="header"><h1>Luxe Wear</h1></div>
        <div class="body">
          <div class="tag">Password Reset</div>
          <p class="subtitle">Use the 6-digit code below to reset your password.<br>This code expires in <strong>10 minutes</strong>.</p>
          <div class="code-box"><div class="code">{code}</div></div>
          <p class="note">If you didn't request a password reset, ignore this email.</p>
          <p class="note">Your password will not change until you complete the reset.</p>
        </div>
        <div class="footer">© {datetime.datetime.now().year} Luxe Wear · All rights reserved</div>
      </div>
    </body></html>
    """
    try:
        send_email(email, "Reset your Luxe Wear password", html)
        return jsonify(ok=True)
    except Exception as e:
        print(f"Reset email error: {e}")
        return jsonify(ok=False, error=str(e)), 500


# ── POST /reset-password  — verify code + set new password ────────────────────
@app.route("/reset-password", methods=["POST"])
def reset_password():
    _, db = _get_firebase()
    if not db:
        return jsonify(ok=False, error="Server not configured for password reset"), 500

    data         = request.get_json(force=True)
    email        = data.get("email", "")
    code         = data.get("code", "")
    new_password = data.get("newPassword", "")

    if not email or not code or not new_password:
        return jsonify(ok=False, error="Missing fields"), 400
    if len(new_password) < 6:
        return jsonify(ok=False, error="Password must be at least 6 characters"), 400

    # Verify code from Firestore
    doc_ref = db.collection("passwordResets").document(email)
    doc     = doc_ref.get()
    if not doc.exists:
        return jsonify(ok=False, error="No reset code found. Please request a new one."), 400

    stored = doc.to_dict()
    if stored.get("code") != code:
        return jsonify(ok=False, error="Incorrect code. Please try again."), 400

    # Check expiry (10 minutes)
    created_at = stored.get("createdAt")
    if created_at:
        now  = datetime.datetime.now(datetime.timezone.utc)
        diff = (now - created_at).total_seconds()
        if diff > 600:
            doc_ref.delete()
            return jsonify(ok=False, error="Code has expired. Please request a new one."), 400

    # Update password via Firebase Admin
    try:
        from firebase_admin import auth as fb_auth
        user = fb_auth.get_user_by_email(email)
        fb_auth.update_user(user.uid, password=new_password)
        doc_ref.delete()
        return jsonify(ok=True)
    except Exception as e:
        print(f"Password reset error: {e}")
        return jsonify(ok=False, error=str(e)), 500


# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return "Luxe Wear Order Bot is running ✅"


if __name__ == "__main__":
    print(f"✅ Server running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
