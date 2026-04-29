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

# Amazon UAE referral fee = 15% across all categories here
# FBA per-unit fee and monthly storage are size/weight-based estimates
MOCK_FEES = {
    "B0F8W72SYT": {"referral_pct": 0.15, "fba_per_unit": 12.0, "storage_monthly": 3.5},
    "B09M69G8X7": {"referral_pct": 0.15, "fba_per_unit":  7.5, "storage_monthly": 2.0},
    "B0FBXBLF9Y": {"referral_pct": 0.15, "fba_per_unit": 13.5, "storage_monthly": 4.0},
    "B0C592JW6D": {"referral_pct": 0.15, "fba_per_unit":  9.5, "storage_monthly": 2.5},
    "B0C43HGC77": {"referral_pct": 0.15, "fba_per_unit":  9.5, "storage_monthly": 2.5},
}

# Mock Sponsored Products campaigns — 30-day window
# Total spend AED 434 | Total attributed sales AED 1,505
_MOCK_CAMPAIGNS = [
    {"Campaign": "SP - Microphone - Broad",  "ASIN": "B0F8W72SYT", "Product": "Microphone",       "Impressions": 8420, "Clicks": 127, "Spend": 89.0,  "Sales": 324.0, "Orders": 3},
    {"Campaign": "SP - Microphone - Exact",  "ASIN": "B0F8W72SYT", "Product": "Microphone",       "Impressions": 3210, "Clicks":  68, "Spend": 52.0,  "Sales": 216.0, "Orders": 2},
    {"Campaign": "SP - Broom Holder",        "ASIN": "B09M69G8X7", "Product": "Broom Holder",     "Impressions": 5640, "Clicks":  89, "Spend": 45.0,  "Sales": 152.0, "Orders": 4},
    {"Campaign": "SP - Bidet - KW",          "ASIN": "B0FBXBLF9Y", "Product": "Bidet",            "Impressions": 6820, "Clicks": 102, "Spend": 78.0,  "Sales": 255.0, "Orders": 3},
    {"Campaign": "SP - Travel Org - Broad",  "ASIN": "B0C592JW6D", "Product": "Travel Org Beige", "Impressions": 9340, "Clicks": 156, "Spend": 112.0, "Sales": 372.0, "Orders": 6},
    {"Campaign": "SP - Travel Org - Exact",  "ASIN": "B0C43HGC77", "Product": "Travel Org Grey",  "Impressions": 4180, "Clicks":  74, "Spend":  58.0, "Sales": 186.0, "Orders": 3},
]

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


def get_fees() -> dict:
    """Returns fee structure per ASIN — real SP-API ProductFees or mock."""
    if not is_live():
        return {k: dict(v) for k, v in MOCK_FEES.items()}

    # TODO: SP-API ProductFees.get_my_fees_estimate per ASIN
    # Falls back to mock until Advertising API is wired up
    return {k: dict(v) for k, v in MOCK_FEES.items()}


def get_ad_performance_30d() -> pd.DataFrame:
    """Returns campaign-level ad performance for last 30 days — real Advertising API or mock."""
    if not is_live():
        df = pd.DataFrame(_MOCK_CAMPAIGNS)
    else:
        # TODO: Amazon Advertising API — requires separate credentials
        # (AMAZON_ADS_CLIENT_ID, AMAZON_ADS_CLIENT_SECRET, AMAZON_ADS_REFRESH_TOKEN)
        df = pd.DataFrame(_MOCK_CAMPAIGNS)

    df["CTR (%)"]  = (df["Clicks"] / df["Impressions"] * 100).round(2)
    df["ACOS (%)"] = (df["Spend"]  / df["Sales"]        * 100).round(1)
    df["ROAS"]     = (df["Sales"]  / df["Spend"]).round(2)
    df["CPC (AED)"] = (df["Spend"] / df["Clicks"]).round(2)
    return df
