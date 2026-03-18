"""
WEBSITE INTEGRATION — example showing how to call the bot server from Python.
If your website backend is Python (e.g. Django / FastAPI), use these helpers.
"""

import requests

BOT_SERVER_URL = "http://localhost:3000"  # ← change to your deployed server URL


def submit_order(full_name, email, phone, location_link, currency, items, total):
    """
    Call this when the customer clicks 'CONTINUE TO PAYMENT'.

    items = list of dicts:
        [{ "name": "Pant", "color": "White", "size": "L", "qty": 1, "price": "6.50" }]
    """
    payload = {
        "fullName": full_name,
        "email": email,
        "phone": phone,
        "locationLink": location_link,
        "currency": currency,   # "USD" or "KHR"
        "items": items,
        "total": total,
    }
    resp = requests.post(f"{BOT_SERVER_URL}/order", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def submit_payment(full_name, phone, transaction_ref, currency, total):
    """
    Call this when the customer submits their ABA transaction reference.
    """
    payload = {
        "fullName": full_name,
        "phone": phone,
        "transactionRef": transaction_ref,
        "currency": currency,
        "total": total,
    }
    resp = requests.post(f"{BOT_SERVER_URL}/payment", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test order notification
    result = submit_order(
        full_name="Sen Visal",
        email="visalsen72@gmail.com",
        phone="012900693",
        location_link="https://www.google.com/maps/@11.5769344,104.9034752,14z",
        currency="USD",
        items=[{"name": "Pant", "color": "White", "size": "L", "qty": 1, "price": "6.50"}],
        total="6.50",
    )
    print("Order sent:", result)

    # Test payment notification
    result = submit_payment(
        full_name="Sen Visal",
        phone="012900693",
        transaction_ref="TXN123456789",
        currency="USD",
        total="6.50",
    )
    print("Payment sent:", result)
