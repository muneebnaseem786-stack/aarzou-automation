"""
Amazon UAE data layer.
Returns real SP-API data when credentials are present; falls back to mock data otherwise.
Mock data is seeded (deterministic) and calibrated to ~AED 4,400/month.
"""

import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

MARKETPLACE_ID = "A2VIGQ35RCS4UG"  # Amazon UAE

PRODUCTS = {
    "B0F8W72SYT": {"name": "Microphone",        "reorder_threshold": 10, "price": 120},
    "B09M69G8X7": {"name": "Broom Holder",       "reorder_threshold": 8,  "price": 38},
    "B0FBXBLF9Y": {"name": "Bidet",              "reorder_threshold": 8,  "price": 85},
    "B0C592JW6D": {"name": "Travel Org Beige",   "reorder_threshold": 5,  "price": 62},
    "B0C43HGC77": {"name": "Travel Org Grey",    "reorder_threshold": 5,  "price": 62},
}

# Realistic mock values — calibrated to ~AED 4,400/month total revenue
_MOCK_INVENTORY = {
    "B0F8W72SYT": 45,
    "B09M69G8X7": 22,
    "B0FBXBLF9Y": 18,
    "B0C592JW6D": 10,   # low — <14 days of stock
    "B0C43HGC77": 5,    # at reorder threshold
}

_MOCK_SALES_7D = {
    "B0F8W72SYT": 2,
    "B09M69G8X7": 4,
    "B0FBXBLF9Y": 3,
    "B0C592JW6D": 4,
    "B0C43HGC77": 2,
}


def is_live() -> bool:
    return bool(os.environ.get("AMAZON_REFRESH_TOKEN"))


def _get_credentials():
    return {
        "lwa_app_id":        os.environ["AMAZON_CLIENT_ID"],
        "lwa_client_secret": os.environ["AMAZON_CLIENT_SECRET"],
        "refresh_token":     os.environ["AMAZON_REFRESH_TOKEN"],
    }


def get_inventory() -> dict:
    """Returns {asin: qty} — real or mock."""
    if not is_live():
        return dict(_MOCK_INVENTORY)

    from sp_api.api import FbaInventory
    from sp_api.base import Marketplaces
    results = {}
    try:
        api = FbaInventory(credentials=_get_credentials(), marketplace=Marketplaces.AE)
        response = api.get_inventory_summaries(
            details=True,
            granularityType="Marketplace",
            granularityId=MARKETPLACE_ID,
            asins=list(PRODUCTS.keys()),
        )
        for item in response.payload.get("inventorySummaries", []):
            asin = item.get("asin")
            qty = item.get("inventoryDetails", {}).get("fulfillableQuantity", 0)
            results[asin] = qty
    except Exception as e:
        print(f"[amazon] Inventory API error: {e} — falling back to mock")
        return dict(_MOCK_INVENTORY)
    return results


def get_sales_7d() -> dict:
    """Returns {asin: units_sold} for the last 7 days — real or mock."""
    if not is_live():
        return dict(_MOCK_SALES_7D)

    from sp_api.api import Orders
    from sp_api.base import Marketplaces
    sales = {asin: 0 for asin in PRODUCTS}
    created_after = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    try:
        api = Orders(credentials=_get_credentials(), marketplace=Marketplaces.AE)
        response = api.get_orders(
            MarketplaceIds=[MARKETPLACE_ID],
            CreatedAfter=created_after,
            OrderStatuses=["Shipped", "Unshipped", "PartiallyShipped"],
        )
        for order in response.payload.get("Orders", []):
            order_id = order["AmazonOrderId"]
            try:
                items = api.get_order_items(order_id).payload.get("OrderItems", [])
                for item in items:
                    asin = item.get("ASIN")
                    if asin in sales:
                        sales[asin] += int(item.get("QuantityOrdered", 0))
            except Exception:
                continue
    except Exception as e:
        print(f"[amazon] Orders API error: {e} — falling back to mock")
        return dict(_MOCK_SALES_7D)
    return sales


def get_daily_revenue_30d() -> pd.DataFrame:
    """
    Returns a DataFrame with columns [date, revenue_aed] for the last 30 days.
    Uses mock data (SP-API doesn't expose daily revenue history directly without storage).
    Seeded so the chart is consistent across refreshes.
    """
    rng = np.random.default_rng(seed=42)

    # Base daily revenue = sum(7d_units / 7 * price) across all products
    base_daily = sum(
        (_MOCK_SALES_7D[asin] / 7) * PRODUCTS[asin]["price"]
        for asin in PRODUCTS
    )

    today = datetime.now(timezone.utc).date()
    dates = [today - timedelta(days=i) for i in range(29, -1, -1)]

    # Add realistic variance: ±25% noise, slight upward trend, weekend dips
    noise = rng.normal(loc=0, scale=base_daily * 0.22, size=30)
    trend = np.linspace(-base_daily * 0.1, base_daily * 0.15, 30)
    weekend_dip = np.array([-base_daily * 0.12 if datetime.strptime(str(d), "%Y-%m-%d").weekday() >= 5 else 0 for d in dates])

    revenues = np.maximum(0, base_daily + noise + trend + weekend_dip)

    return pd.DataFrame({"date": dates, "revenue_aed": revenues.round(2)})


def build_inventory_df(inventory: dict, sales_7d: dict) -> pd.DataFrame:
    """Combines inventory and sales into a single DataFrame for display."""
    rows = []
    for asin, meta in PRODUCTS.items():
        units = inventory.get(asin, 0)
        sold = sales_7d.get(asin, 0)
        velocity = round(sold / 7, 2)
        threshold = meta["reorder_threshold"]

        if velocity > 0:
            days_left = round(units / velocity)
        elif units > 0:
            days_left = 999
        else:
            days_left = 0

        if units <= threshold:
            status = "REORDER NOW"
        elif days_left < 14:
            status = "LOW"
        elif sold == 0:
            status = "ZERO SALES"
        else:
            status = "OK"

        rows.append({
            "Product":      meta["name"],
            "ASIN":         asin,
            "Stock":        units,
            "Reorder @":    threshold,
            "Sold (7d)":    sold,
            "Velocity":     f"{velocity}/day",
            "Days Left":    days_left if days_left < 999 else "∞",
            "Status":       status,
            "_velocity_raw": velocity,
            "_days_left_raw": days_left,
            "_price":       meta["price"],
        })
    return pd.DataFrame(rows)
