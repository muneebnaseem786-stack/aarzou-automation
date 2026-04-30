"""
Data fetching layer — pulls from Amazon SP-API and Noon API.
Returns clean dataframes for the dashboard to display.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import pandas as pd


ASINS = {
    "B0F8W72SYT": "Microphone",
    "B09M69G8X7": "Broom Holder",
    "B0FBXBLF9Y": "Bidet",
    "B0C592JW6D": "Travel Org Beige",
    "B0C43HGC77": "Travel Org Grey",
}

MARKETPLACE_ID = "A2VIGQ35RCS4UG"  # Amazon UAE


def amazon_ready() -> bool:
    return bool(os.environ.get("AMAZON_REFRESH_TOKEN"))


def noon_ready() -> bool:
    return bool(os.environ.get("NOON_API_KEY"))


# ── Amazon ────────────────────────────────────────────────────────────────────

def get_amazon_credentials():
    return {
        "lwa_app_id":        os.environ["AMAZON_CLIENT_ID"],
        "lwa_client_secret": os.environ["AMAZON_CLIENT_SECRET"],
        "refresh_token":     os.environ["AMAZON_REFRESH_TOKEN"],
    }


def fetch_amazon_inventory() -> pd.DataFrame:
    """Returns DataFrame: product, asin, units_available"""
    from sp_api.api import FbaInventory
    from sp_api.base import Marketplaces
    rows = []
    try:
        api = FbaInventory(credentials=get_amazon_credentials(), marketplace=Marketplaces.AE)
        response = api.get_inventory_summaries(
            details=True,
            granularityType="Marketplace",
            granularityId=MARKETPLACE_ID,
            asins=list(ASINS.keys()),
        )
        for item in response.payload.get("inventorySummaries", []):
            asin = item.get("asin")
            rows.append({
                "product":         ASINS.get(asin, asin),
                "asin":            asin,
                "units_available": item.get("inventoryDetails", {}).get("fulfillableQuantity", 0),
                "inbound_units":   item.get("inventoryDetails", {}).get("inboundWorkingQuantity", 0),
                "platform":        "Amazon",
            })
    except Exception as e:
        print(f"Amazon inventory error: {e}")
    return pd.DataFrame(rows)


def fetch_amazon_orders(days: int = 30) -> pd.DataFrame:
    """Returns DataFrame: date, asin, product, units, revenue_aed"""
    from sp_api.api import Orders
    from sp_api.base import Marketplaces
    rows = []
    created_after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        api = Orders(credentials=get_amazon_credentials(), marketplace=Marketplaces.AE)
        response = api.get_orders(
            MarketplaceIds=[MARKETPLACE_ID],
            CreatedAfter=created_after,
            OrderStatuses=["Shipped", "Unshipped", "PartiallyShipped"],
        )
        for order in response.payload.get("Orders", []):
            order_id = order["AmazonOrderId"]
            order_date = order.get("PurchaseDate", "")[:10]
            try:
                items_resp = api.get_order_items(order_id)
                for item in items_resp.payload.get("OrderItems", []):
                    asin = item.get("ASIN")
                    qty = int(item.get("QuantityOrdered", 0))
                    price = float(item.get("ItemPrice", {}).get("Amount", 0))
                    rows.append({
                        "date":        order_date,
                        "asin":        asin,
                        "product":     ASINS.get(asin, asin),
                        "units":       qty,
                        "revenue_aed": price,
                        "platform":    "Amazon",
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"Amazon orders error: {e}")
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


# ── Noon ──────────────────────────────────────────────────────────────────────

def fetch_noon_orders(days: int = 30) -> pd.DataFrame:
    """
    Noon Commercial API — fetches recent orders.
    Endpoint: GET /v2/orders  (base: https://api.noon.partners)
    """
    import requests
    rows = []
    try:
        api_key    = os.environ["NOON_API_KEY"]
        api_secret = os.environ["NOON_API_SECRET"]
        base_url   = "https://api.noon.partners"
        created_after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

        headers = {
            "Authorization": f"Basic {api_key}:{api_secret}",
            "Content-Type":  "application/json",
        }
        params = {"from_date": created_after, "limit": 200}
        response = requests.get(f"{base_url}/v2/orders", headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        for order in data.get("orders", []):
            for item in order.get("items", []):
                rows.append({
                    "date":        order.get("created_at", "")[:10],
                    "product":     item.get("name", "Unknown"),
                    "sku":         item.get("sku", ""),
                    "units":       int(item.get("quantity", 0)),
                    "revenue_aed": float(item.get("unit_price", 0)) * int(item.get("quantity", 0)),
                    "platform":    "Noon",
                })
    except Exception as e:
        print(f"Noon orders error: {e}")

    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_noon_inventory() -> pd.DataFrame:
    """Noon inventory levels from Commercial API."""
    import requests
    rows = []
    try:
        api_key    = os.environ["NOON_API_KEY"]
        api_secret = os.environ["NOON_API_SECRET"]
        headers    = {"Authorization": f"Basic {api_key}:{api_secret}"}
        response   = requests.get("https://api.noon.partners/v2/products", headers=headers, timeout=30)
        response.raise_for_status()
        for item in response.json().get("products", []):
            rows.append({
                "product":         item.get("name", "Unknown"),
                "sku":             item.get("sku", ""),
                "units_available": int(item.get("quantity", 0)),
                "platform":        "Noon",
            })
    except Exception as e:
        print(f"Noon inventory error: {e}")
    return pd.DataFrame(rows)


# ── Combined helpers ──────────────────────────────────────────────────────────

def get_combined_revenue(days: int = 30) -> pd.DataFrame:
    """Combined Amazon + Noon revenue, grouped by date."""
    frames = []
    if amazon_ready():
        frames.append(fetch_amazon_orders(days))
    if noon_ready():
        frames.append(fetch_noon_orders(days))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return df


def get_combined_inventory() -> pd.DataFrame:
    frames = []
    if amazon_ready():
        frames.append(fetch_amazon_inventory())
    if noon_ready():
        frames.append(fetch_noon_inventory())
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
