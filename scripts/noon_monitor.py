"""
AARZOU Noon UAE Monitor
Runs daily via GitHub Actions — checks inventory for all active SKUs.
Sends an alert email only if any SKU is below threshold or offer is inactive.
"""

import csv
import io
import json
import os
import time
import uuid
from datetime import datetime, timezone

import jwt
import requests

from scripts.utils.email_utils import send_email

BASE = "https://noon-api-gateway.noon.partners"

SKUS = {
    "Microphone": {"threshold": 10},
    "Mop Holder": {"threshold": 8},
    "Bidet Set":  {"threshold": 8},
}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_noon_session(creds: dict) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "AARZOU-Dashboard/1.0",
        "Content-Type": "application/json",
    })
    token = jwt.encode(
        {
            "sub": creds["key_id"],
            "iat": int(time.time()),
            "jti": str(uuid.uuid4()),
        },
        creds["private_key"],
        algorithm="RS256",
    )
    r = session.post(
        f"{BASE}/identity/public/v1/api/login",
        json={"token": token, "default_project_code": creds["project_code"]},
        timeout=30,
    )
    r.raise_for_status()
    return session


# ---------------------------------------------------------------------------
# Inventory check
# ---------------------------------------------------------------------------

def check_sku(session: requests.Session, partner_sku: str) -> dict:
    """Returns dict with keys: stock (int|None), active (bool), error (str|None)."""
    try:
        r = session.get(f"{BASE}/offer/v1/product/{partner_sku}", timeout=30)
        r.raise_for_status()
        data = r.json()
        offers = data.get("offers", [])
        ae_offers = [o for o in offers if o.get("country_code") == "ae"]

        if not ae_offers:
            return {"stock": None, "active": False, "error": "No AE offer found"}

        offer = ae_offers[0]
        stock = offer.get("active_net_stock", 0)
        # An offer is "live" if it has a status of ACTIVE/live and stock > 0
        status = str(offer.get("offer_status", "")).lower()
        active = status in ("active", "live", "published")
        return {"stock": stock, "active": active, "error": None}

    except Exception as e:
        return {"stock": None, "active": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(results: dict) -> tuple[str, list[str]]:
    """Returns (html_body, alerts_list)."""
    alerts = []
    rows = []

    for sku, meta in SKUS.items():
        threshold = meta["threshold"]
        info = results.get(sku, {"stock": None, "active": False, "error": "Not checked"})
        stock = info["stock"]
        active = info["active"]
        error = info["error"]

        if error:
            status_label = f"ERROR: {error}"
            row_color = "#fff3cd"
            alerts.append(f"{sku}: error fetching data — {error}")
        elif not active:
            status_label = "OFFER INACTIVE / NOT LIVE"
            row_color = "#f8d7da"
            alerts.append(f"{sku}: offer is inactive or not live on Noon AE")
        elif stock is not None and stock <= threshold:
            status_label = f"LOW STOCK ({stock} units — threshold {threshold})"
            row_color = "#f8d7da"
            alerts.append(f"{sku}: only {stock} units left (threshold: {threshold})")
        else:
            status_label = "OK"
            row_color = "#d4edda"

        stock_display = str(stock) if stock is not None else "N/A"
        rows.append(f"""
        <tr style="background:{row_color}">
            <td style="padding:10px"><b>{sku}</b></td>
            <td style="padding:10px;text-align:center">{stock_display}</td>
            <td style="padding:10px;text-align:center">{threshold}</td>
            <td style="padding:10px;text-align:center">{"Yes" if active else "No"}</td>
            <td style="padding:10px">{status_label}</td>
        </tr>""")

    date_str = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    action_block = ""
    if alerts:
        action_block = (
            "<h3 style='color:#c0392b'>ACTION REQUIRED</h3><ul>"
            + "".join(f"<li>{a}</li>" for a in alerts)
            + "</ul>"
        )

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:720px;margin:auto;color:#333">
    <h2 style="color:#2c3e50">AARZOU Noon Inventory Monitor — {date_str}</h2>
    <table border="1" cellpadding="0" cellspacing="0" width="100%"
           style="border-collapse:collapse;font-size:14px;border-color:#ddd">
        <thead style="background:#2c3e50;color:#fff">
            <tr>
                <th style="padding:10px;text-align:left">Product (SKU)</th>
                <th style="padding:10px">Stock</th>
                <th style="padding:10px">Threshold</th>
                <th style="padding:10px">Offer Live?</th>
                <th style="padding:10px;text-align:left">Status</th>
            </tr>
        </thead>
        <tbody>{"".join(rows)}</tbody>
    </table>
    {action_block}
    <p style="color:#999;font-size:12px;margin-top:24px">
        Auto-generated · AARZOU Monitor · Noon UAE · daily 7am UAE
    </p>
    </body></html>
    """
    return html, alerts


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print(f"[{datetime.now()}] Noon monitor starting...")

    creds_json = os.environ.get("NOON_CREDENTIALS_JSON")
    if not creds_json:
        print("NOON_CREDENTIALS_JSON not set — skipping Noon monitor.")
        return

    creds = json.loads(creds_json)

    try:
        session = get_noon_session(creds)
    except Exception as e:
        send_email(
            subject="AARZOU Noon Monitor — Auth Failed",
            html_body=f"<h2>Noon API authentication failed.</h2><p>Error: {e}</p>",
        )
        print(f"Auth failed: {e}")
        return

    results = {}
    for sku in SKUS:
        results[sku] = check_sku(session, sku)
        print(f"  {sku}: {results[sku]}")

    html_body, alerts = build_report(results)

    if not alerts:
        print("All Noon SKUs OK — no email sent.")
        return

    # Build subject from first alert SKU
    first_alert_sku = next(
        (s for s in SKUS if any(s in a for a in alerts)), "Products"
    )
    first_result = results.get(first_alert_sku, {})
    stock_val = first_result.get("stock")
    if stock_val is not None:
        subject = f"Noon Stock Alert — {first_alert_sku} at {stock_val} units"
    else:
        subject = f"Noon Alert — {first_alert_sku} offer inactive or error"

    send_email(subject=subject, html_body=html_body)
    print(f"Alert email sent. {len(alerts)} issue(s) flagged.")
    for a in alerts:
        print(f"  -> {a}")


if __name__ == "__main__":
    main()
