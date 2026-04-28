"""
AARZOU Amazon UAE Monitor
Runs daily via GitHub Actions — checks inventory, sales velocity, and flags issues.
Sends a daily email digest to muneebnaseem786@gmail.com
"""

import os
from datetime import datetime, timedelta, timezone
from scripts.utils.email_utils import send_email

MARKETPLACE_ID = "A2VIGQ35RCS4UG"  # Amazon UAE

ASINS = {
    "B0F8W72SYT": {"name": "Microphone",       "reorder_threshold": 10},
    "B09M69G8X7": {"name": "Broom Holder",      "reorder_threshold": 8},
    "B0FBXBLF9Y": {"name": "Bidet",             "reorder_threshold": 8},
    "B0C592JW6D": {"name": "Travel Org Beige",  "reorder_threshold": 5},
    "B0C43HGC77": {"name": "Travel Org Grey",   "reorder_threshold": 5},
}


def get_credentials():
    return {
        "lwa_app_id":        os.environ["AMAZON_CLIENT_ID"],
        "lwa_client_secret": os.environ["AMAZON_CLIENT_SECRET"],
        "refresh_token":     os.environ["AMAZON_REFRESH_TOKEN"],
    }


def get_inventory() -> dict:
    from sp_api.api import FbaInventory
    from sp_api.base import Marketplaces, SellingApiException
    results = {}
    try:
        api = FbaInventory(credentials=get_credentials(), marketplace=Marketplaces.AE)
        response = api.get_inventory_summaries(
            details=True,
            granularityType="Marketplace",
            granularityId=MARKETPLACE_ID,
            asins=list(ASINS.keys()),
        )
        for item in response.payload.get("inventorySummaries", []):
            asin = item.get("asin")
            qty = item.get("inventoryDetails", {}).get("fulfillableQuantity", 0)
            results[asin] = qty
    except Exception as e:
        print(f"Inventory API error: {e}")
    return results


def get_sales_last_7_days() -> dict:
    from sp_api.api import Orders
    from sp_api.base import Marketplaces, SellingApiException
    sales = {asin: 0 for asin in ASINS}
    created_after = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    try:
        api = Orders(credentials=get_credentials(), marketplace=Marketplaces.AE)
        response = api.get_orders(
            MarketplaceIds=[MARKETPLACE_ID],
            CreatedAfter=created_after,
            OrderStatuses=["Shipped", "Unshipped", "PartiallyShipped"],
        )
        for order in response.payload.get("Orders", []):
            order_id = order["AmazonOrderId"]
            try:
                items_response = api.get_order_items(order_id)
                for item in items_response.payload.get("OrderItems", []):
                    asin = item.get("ASIN")
                    if asin in sales:
                        sales[asin] += int(item.get("QuantityOrdered", 0))
            except Exception:
                continue
    except Exception as e:
        print(f"Orders API error: {e}")
    return sales


def build_report(inventory: dict, sales: dict) -> tuple:
    alerts = []
    rows = []

    for asin, meta in ASINS.items():
        name = meta["name"]
        threshold = meta["reorder_threshold"]
        units = inventory.get(asin, "?")
        sold_7d = sales.get(asin, 0)
        daily_velocity = round(sold_7d / 7, 1)

        days_remaining = "?"
        if isinstance(units, int) and daily_velocity > 0:
            days_remaining = round(units / daily_velocity)
        elif isinstance(units, int) and daily_velocity == 0:
            days_remaining = "inf"

        status = "OK"
        if isinstance(units, int) and units <= threshold:
            status = "REORDER NOW"
            alerts.append(f"{name} ({asin}): only {units} units left")
        elif isinstance(days_remaining, int) and days_remaining < 14:
            status = "LOW — reorder soon"
            alerts.append(f"{name} ({asin}): ~{days_remaining} days of stock left")
        elif sold_7d == 0:
            status = "ZERO SALES (7d)"
            alerts.append(f"{name} ({asin}): no sales in last 7 days — check listing/Buy Box")

        rows.append(f"""
        <tr>
            <td><b>{name}</b><br><small>{asin}</small></td>
            <td style="text-align:center">{units}</td>
            <td style="text-align:center">{sold_7d}</td>
            <td style="text-align:center">{daily_velocity}/day</td>
            <td style="text-align:center">{days_remaining}</td>
            <td>{status}</td>
        </tr>""")

    date_str = datetime.now(timezone.utc).strftime("%d %b %Y")
    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto">
    <h2>AARZOU Amazon Daily Monitor — {date_str}</h2>
    <table border="1" cellpadding="8" cellspacing="0" width="100%"
           style="border-collapse:collapse;font-size:14px">
        <thead style="background:#f0f0f0">
            <tr>
                <th>Product</th><th>Stock</th><th>Sold (7d)</th>
                <th>Velocity</th><th>Days Left</th><th>Status</th>
            </tr>
        </thead>
        <tbody>{"".join(rows)}</tbody>
    </table>
    {"<h3 style='color:red'>ACTION REQUIRED</h3><ul>" + "".join(f"<li>{a}</li>" for a in alerts) + "</ul>" if alerts else "<p style='color:green'>No urgent issues today.</p>"}
    <p style="color:#888;font-size:12px">Auto-generated · AARZOU Monitor · Amazon UAE · 7am UAE daily</p>
    </body></html>
    """
    return html, alerts


def main():
    print(f"[{datetime.now()}] AARZOU Monitor starting...")

    if not os.environ.get("AMAZON_REFRESH_TOKEN"):
        send_email(
            subject="AARZOU Monitor — Email Test Successful",
            html_body="<h2>Email delivery confirmed.</h2><p>Amazon SP-API credentials not yet added. Add AMAZON_CLIENT_ID, AMAZON_CLIENT_SECRET, AMAZON_REFRESH_TOKEN to GitHub Secrets once your SP-API application is approved — the monitor will go live automatically.</p>"
        )
        print("SP-API credentials not set — sent test email.")
        return

    inventory = get_inventory()
    sales = get_sales_last_7_days()
    html_body, alerts = build_report(inventory, sales)

    subject = "AARZOU ALERT — Action Required" if alerts else "AARZOU Daily Monitor — All Good"
    send_email(subject=subject, html_body=html_body)

    print(f"Done. Alerts: {len(alerts)}")
    for a in alerts:
        print(f"  -> {a}")


if __name__ == "__main__":
    main()
