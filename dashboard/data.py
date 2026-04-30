"""
Data fetching layer — pulls from Amazon SP-API and Noon API.
Returns clean dataframes for the dashboard to display.
"""

import os
import json
import time
import jwt
import requests
from datetime import datetime, timedelta, timezone
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
    return bool(os.environ.get("NOON_CREDENTIALS_JSON"))


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

NOON_BASE_URL = "https://noon-api-gateway.noon.partners"

NOON_PARTNER_SKUS = {
    "Microphone": "Microphone",
    "Mop Holder": "Broom Holder",
    "Bidet Set":  "Bidet",
}

_noon_session = None
_noon_session_time = 0
SESSION_TTL = 3600  # re-login every hour


def _get_noon_session() -> requests.Session:
    global _noon_session, _noon_session_time
    if _noon_session and (time.time() - _noon_session_time) < SESSION_TTL:
        return _noon_session
    import uuid
    creds = json.loads(os.environ["NOON_CREDENTIALS_JSON"])
    token = jwt.encode(
        {"sub": creds["key_id"], "iat": int(time.time()), "jti": str(uuid.uuid4())},
        creds["private_key"], algorithm="RS256",
    )
    session = requests.Session()
    session.headers.update({"User-Agent": "AARZOU-Dashboard/1.0", "Content-Type": "application/json"})
    r = session.post(
        f"{NOON_BASE_URL}/identity/public/v1/api/login",
        json={"token": token, "default_project_code": creds["project_code"]},
        timeout=30,
    )
    r.raise_for_status()
    _noon_session = session
    _noon_session_time = time.time()
    return session


def _noon_create_and_download_export(session, category_code: str, params: dict) -> str:
    """Create an export job and return the CSV text when complete."""
    r = session.post(f"{NOON_BASE_URL}/impex/v1/export/create",
                     json={"export_category_code": category_code, "params": params}, timeout=30)
    r.raise_for_status()
    export_code = r.json()["export_code"]
    for _ in range(24):  # wait up to 2 min
        time.sleep(5)
        st = session.post(f"{NOON_BASE_URL}/impex/v1/export/status",
                          json={"export_code": export_code}, timeout=30).json()
        if st.get("export_status") == "COMPLETE" and st.get("download_url"):
            return requests.get(st["download_url"], timeout=60).text
    raise TimeoutError(f"Export {export_code} did not complete in time")


def fetch_noon_orders(days: int = 30) -> pd.DataFrame:
    """Noon sales data via productviewsandsalesdata export."""
    rows = []
    try:
        import io
        session = _get_noon_session()
        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")
        csv_text = _noon_create_and_download_export(session,
            "noon_catalog_reports_productviewsandsalesdata",
            {"country": "ae", "from_date": from_date, "to_date": to_date, "lang": "en"},
        )
        df_raw = pd.read_csv(io.StringIO(csv_text))
        for _, row in df_raw.iterrows():
            units = int(row.get("Shipped_Units", 0) or 0)
            revenue = float(row.get("Revenue_Shipped", 0) or 0)
            if units > 0:
                rows.append({
                    "date":        row.get("Visit_Date", ""),
                    "product":     row.get("Partner_SKU", "Unknown"),
                    "sku":         row.get("SKU", ""),
                    "units":       units,
                    "revenue_aed": revenue,
                    "platform":    "Noon",
                })
    except Exception as e:
        print(f"Noon orders error: {e}")
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_noon_inventory() -> pd.DataFrame:
    """Noon inventory via offer endpoint per SKU."""
    rows = []
    try:
        session = _get_noon_session()
        for partner_sku, product_name in NOON_PARTNER_SKUS.items():
            try:
                r = session.get(f"{NOON_BASE_URL}/offer/v1/product/{partner_sku}", timeout=30)
                if r.status_code != 200:
                    continue
                data = r.json()
                for offer in data.get("offers", []):
                    if offer.get("country_code") == "ae":
                        rows.append({
                            "product":         product_name,
                            "sku":             partner_sku,
                            "units_available": int(offer.get("active_net_stock", 0)),
                            "platform":        "Noon",
                        })
                        break
            except Exception:
                continue
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
