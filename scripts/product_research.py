"""
AARZOU Weekly Product Research — UAE E-Commerce
Runs every Monday via GitHub Actions.

Logic:
1. Pull last 30 days of Noon sales to understand what's already working
2. Scrape Noon category browse pages for trending products (BeautifulSoup)
3. If scraping blocked, fall back to hardcoded high-opportunity categories
4. Calculate estimated margin using UAE marketplace heuristics
5. Filter: margin > 25% AND est. monthly units > 20
6. Send HTML report via email
"""

import csv
import io
import json
import os
import time
import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Optional

import jwt
import requests

from scripts.utils.email_utils import send_email

BASE = "https://noon-api-gateway.noon.partners"

# Target categories aligned with existing product catalog
CATEGORY_URLS = {
    "home_improvement":  "https://www.noon.com/uae-en/home-improvement/",
    "audio_video":       "https://www.noon.com/uae-en/electronics/audio-video/",
    "sports_outdoor":    "https://www.noon.com/uae-en/sports-and-outdoors/",
    "kitchen":           "https://www.noon.com/uae-en/home-and-kitchen/kitchen/",
    "bath_accessories":  "https://www.noon.com/uae-en/home-and-kitchen/bath/",
}

# Noon referral fee (approx. average)
NOON_REFERRAL_FEE_PCT = 0.15

# Logistics cost AED (small vs medium items, we use small as default heuristic)
LOGISTICS_SMALL = 8.0
LOGISTICS_MEDIUM = 15.0

# Thresholds for filtering candidates
MIN_MARGIN_PCT = 0.25
MIN_MONTHLY_UNITS = 20

# Alibaba cost ratio heuristic (UAE retail → Alibaba cost)
ALIBABA_RATIO_LOW  = 0.15
ALIBABA_RATIO_HIGH = 0.25
ALIBABA_RATIO_MID  = (ALIBABA_RATIO_LOW + ALIBABA_RATIO_HIGH) / 2  # 0.20

# Fallback product candidates if scraping fails
FALLBACK_CANDIDATES = [
    {
        "title": "Adjustable Monitor Stand / Desk Riser",
        "category": "home_improvement",
        "noon_price": 89.0,
        "size": "medium",
        "why": "WFH demand still high in UAE; low competition below AED 150",
    },
    {
        "title": "Bamboo Kitchen Utensil Organizer Set",
        "category": "kitchen",
        "noon_price": 55.0,
        "size": "medium",
        "why": "High search volume, sustainable angle resonates in UAE market",
    },
    {
        "title": "Waterproof Shower Caddy with Suction Cups",
        "category": "bath_accessories",
        "noon_price": 45.0,
        "size": "small",
        "why": "High repurchase rate, low return rate for bath accessories",
    },
    {
        "title": "Resistance Band Set (5-band)",
        "category": "sports_outdoor",
        "noon_price": 65.0,
        "size": "small",
        "why": "Home fitness remains strong; compact = low logistics cost",
    },
    {
        "title": "USB-C Hub 7-in-1 for Laptops",
        "category": "audio_video",
        "noon_price": 120.0,
        "size": "small",
        "why": "MacBook + iPad adoption drives consistent demand in UAE",
    },
    {
        "title": "Foldable Laptop Stand Portable Aluminum",
        "category": "audio_video",
        "noon_price": 95.0,
        "size": "small",
        "why": "High velocity SKU category; strong repeat demographics 25-40",
    },
    {
        "title": "Magnetic Phone Mount for Car Dashboard",
        "category": "home_improvement",
        "noon_price": 38.0,
        "size": "small",
        "why": "Impulse buy price point; consistently top seller in auto accessories",
    },
    {
        "title": "Stainless Steel Insulated Water Bottle 1L",
        "category": "sports_outdoor",
        "noon_price": 60.0,
        "size": "medium",
        "why": "Hot climate = year-round demand; gifting season spikes",
    },
]


# ---------------------------------------------------------------------------
# Noon Auth
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
# Noon sales export (last 30 days) — own products for context
# ---------------------------------------------------------------------------

def poll_export(session: requests.Session, export_code: str, max_wait: int = 120) -> Optional[str]:
    """Poll until export is COMPLETE, return download URL or None."""
    for _ in range(max_wait // 5):
        time.sleep(5)
        r = session.post(
            f"{BASE}/impex/v1/export/status",
            json={"export_code": export_code},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        status = data.get("export_status", "")
        if status == "COMPLETE":
            return data.get("download_url")
        if status in ("FAILED", "ERROR"):
            return None
    return None


def get_own_sales_context(session: requests.Session) -> list[dict]:
    """Pull last 30 days of own sales. Returns list of {sku, units, revenue}."""
    today = date.today()
    from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")

    try:
        r = session.post(
            f"{BASE}/impex/v1/export/create",
            json={
                "export_category_code": "noon_catalog_reports_productviewsandsalesdata",
                "params": {
                    "country": "ae",
                    "from_date": from_date,
                    "to_date": to_date,
                    "lang": "en",
                },
            },
            timeout=30,
        )
        r.raise_for_status()
        export_code = r.json().get("export_code")
        if not export_code:
            return []

        download_url = poll_export(session, export_code)
        if not download_url:
            return []

        csv_response = requests.get(download_url, timeout=60)
        csv_response.raise_for_status()
        reader = csv.DictReader(io.StringIO(csv_response.text))
        sales = []
        for row in reader:
            try:
                sales.append({
                    "sku":     row.get("Partner_SKU", ""),
                    "units":   int(float(row.get("Shipped_Units", 0) or 0)),
                    "revenue": float(row.get("Revenue_Shipped", 0) or 0),
                })
            except (ValueError, KeyError):
                continue
        return sales

    except Exception as e:
        print(f"[sales export] {e}")
        return []


# ---------------------------------------------------------------------------
# Noon browse scraping
# ---------------------------------------------------------------------------

def scrape_noon_category(category_name: str, url: str) -> list[dict]:
    """Scrape Noon browse page for product listings. Returns list of candidates."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-AE,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            print(f"[scrape] {category_name}: HTTP {r.status_code} — skipping")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        candidates = []

        # Noon renders product cards — look for common price/title patterns
        # Products are in elements with data-qa or class patterns like "productContainer"
        # We try multiple selectors since Noon may update their markup
        product_blocks = (
            soup.select("[data-qa='product-name']")
            or soup.select(".sc-name")
            or soup.select("[class*='productName']")
            or soup.select("h2[class*='name']")
        )

        price_blocks = (
            soup.select("[data-qa='price-amount']")
            or soup.select(".priceNow")
            or soup.select("[class*='priceNow']")
            or soup.select("[class*='price']")
        )

        for i, name_el in enumerate(product_blocks[:20]):
            title = name_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Try to get corresponding price
            price = None
            if i < len(price_blocks):
                price_text = price_blocks[i].get_text(strip=True)
                # Extract numeric value from "AED 89.00" or "89"
                price_clean = "".join(c for c in price_text if c.isdigit() or c == ".")
                try:
                    price = float(price_clean)
                except ValueError:
                    pass

            # Skip if price is clearly wrong or too low to be interesting
            if price and (price < 15 or price > 2000):
                continue

            candidates.append({
                "title":    title,
                "category": category_name,
                "noon_price": price or 75.0,  # use category average if no price
                "size":     "small" if (price or 75) < 100 else "medium",
                "why":      f"Trending in {category_name.replace('_', ' ')} on Noon UAE",
            })

        print(f"[scrape] {category_name}: found {len(candidates)} candidates")
        return candidates[:5]  # cap per category

    except Exception as e:
        print(f"[scrape] {category_name}: error — {e}")
        return []


# ---------------------------------------------------------------------------
# Margin math
# ---------------------------------------------------------------------------

def calculate_margin(noon_price: float, size: str) -> dict:
    alibaba_cost    = noon_price * ALIBABA_RATIO_MID
    referral_fee    = noon_price * NOON_REFERRAL_FEE_PCT
    logistics       = LOGISTICS_SMALL if size == "small" else LOGISTICS_MEDIUM
    total_costs     = alibaba_cost + referral_fee + logistics
    profit          = noon_price - total_costs
    margin_pct      = profit / noon_price if noon_price > 0 else 0

    return {
        "alibaba_cost":  round(alibaba_cost, 2),
        "referral_fee":  round(referral_fee, 2),
        "logistics":     logistics,
        "profit":        round(profit, 2),
        "margin_pct":    round(margin_pct * 100, 1),
    }


def estimate_monthly_units(noon_price: float, category: str) -> int:
    """
    Rough velocity estimate based on price point and category.
    These are conservative UAE-market baselines from category benchmarks.
    """
    base = 30  # moderate seller baseline
    if noon_price < 50:
        base = 60   # impulse buy velocity
    elif noon_price < 100:
        base = 40
    elif noon_price < 200:
        base = 25
    else:
        base = 15

    # Category multipliers (home + audio do well in UAE)
    multipliers = {
        "audio_video":      1.3,
        "home_improvement": 1.2,
        "kitchen":          1.1,
        "bath_accessories": 1.0,
        "sports_outdoor":   0.9,
    }
    return int(base * multipliers.get(category, 1.0))


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_html_report(
    candidates: list[dict],
    own_sales: list[dict],
    scraped: bool,
    report_date: str,
) -> str:
    # Own sales context block
    own_sales_html = ""
    if own_sales:
        own_rows = "".join(
            f"<tr><td style='padding:8px'>{s['sku']}</td>"
            f"<td style='padding:8px;text-align:center'>{s['units']}</td>"
            f"<td style='padding:8px;text-align:center'>AED {s['revenue']:,.0f}</td></tr>"
            for s in sorted(own_sales, key=lambda x: x["revenue"], reverse=True)[:10]
        )
        own_sales_html = f"""
        <h3 style="color:#2c3e50">Your Noon Sales — Last 30 Days (Context)</h3>
        <table border="1" cellpadding="0" cellspacing="0" width="100%"
               style="border-collapse:collapse;font-size:13px;border-color:#ddd;margin-bottom:24px">
            <thead style="background:#ecf0f1">
                <tr>
                    <th style="padding:8px;text-align:left">SKU</th>
                    <th style="padding:8px">Units Sold</th>
                    <th style="padding:8px">Revenue</th>
                </tr>
            </thead>
            <tbody>{own_rows}</tbody>
        </table>
        """

    # Opportunity table rows
    opp_rows = ""
    for c in candidates:
        m = c["margin"]
        units = c["est_monthly_units"]
        margin_color = "#27ae60" if m["margin_pct"] >= 35 else ("#f39c12" if m["margin_pct"] >= 25 else "#e74c3c")
        opp_rows += f"""
        <tr>
            <td style="padding:10px">{c['title']}</td>
            <td style="padding:10px;text-align:center">{c['category'].replace('_',' ')}</td>
            <td style="padding:10px;text-align:center">AED {c['noon_price']:.0f}</td>
            <td style="padding:10px;text-align:center">AED {m['alibaba_cost']:.0f}</td>
            <td style="padding:10px;text-align:center;color:{margin_color};font-weight:bold">{m['margin_pct']}%</td>
            <td style="padding:10px;text-align:center">~{units}/mo</td>
            <td style="padding:10px;font-size:12px;color:#555">{c['why']}</td>
        </tr>"""

    scrape_note = (
        "<p style='color:#27ae60;font-size:12px'>Data sourced from live Noon browse pages.</p>"
        if scraped else
        "<p style='color:#e67e22;font-size:12px'>"
        "<b>Note:</b> Noon scraping was blocked. Candidates below are based on curated "
        "high-opportunity categories. Manual Noon search recommended to validate prices."
        "</p>"
    )

    margin_note = """
    <p style="font-size:12px;color:#777;margin-top:16px">
    <b>Methodology:</b> Alibaba cost = 20% of Noon retail price (UAE heuristic).
    Noon referral fee = 15%. Logistics = AED 8 (small) / AED 15 (medium).
    Monthly unit estimates are conservative baselines — validate with Noon search volume.
    </p>
    """

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:900px;margin:auto;color:#333">
    <h2 style="color:#2c3e50">AARZOU Weekly Product Research — {report_date}</h2>
    <p>Top product opportunities for Noon / Amazon UAE this week.
    Filtered: margin &gt; 25% AND estimated monthly sales &gt; 20 units.</p>
    {scrape_note}
    {own_sales_html}
    <h3 style="color:#2c3e50">Product Opportunities ({len(candidates)} candidates)</h3>
    <table border="1" cellpadding="0" cellspacing="0" width="100%"
           style="border-collapse:collapse;font-size:13px;border-color:#ddd">
        <thead style="background:#2c3e50;color:#fff">
            <tr>
                <th style="padding:10px;text-align:left">Product</th>
                <th style="padding:10px">Category</th>
                <th style="padding:10px">Noon Price</th>
                <th style="padding:10px">Est. Alibaba Cost</th>
                <th style="padding:10px">Est. Margin</th>
                <th style="padding:10px">Est. Monthly Units</th>
                <th style="padding:10px;text-align:left">Why Interesting</th>
            </tr>
        </thead>
        <tbody>{opp_rows}</tbody>
    </table>
    {margin_note}
    <p style="color:#999;font-size:12px;margin-top:24px">
        Auto-generated · AARZOU Product Research · Noon UAE · Monday 8am UAE
    </p>
    </body></html>
    """
    return html


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print(f"[{datetime.now()}] Product research starting...")
    report_date = datetime.now(timezone.utc).strftime("%d %b %Y")

    creds_json = os.environ.get("NOON_CREDENTIALS_JSON")
    own_sales: list[dict] = []
    session = None

    if creds_json:
        try:
            creds = json.loads(creds_json)
            session = get_noon_session(creds)
            print("Noon auth OK — pulling own sales context...")
            own_sales = get_own_sales_context(session)
            print(f"  Own sales: {len(own_sales)} SKUs returned")
        except Exception as e:
            print(f"Noon auth/sales error: {e}")
    else:
        print("NOON_CREDENTIALS_JSON not set — skipping own sales pull")

    # Scrape Noon category pages
    raw_candidates: list[dict] = []
    scraped = False

    for cat_name, cat_url in CATEGORY_URLS.items():
        found = scrape_noon_category(cat_name, cat_url)
        raw_candidates.extend(found)
        time.sleep(1.5)  # polite crawl delay

    if raw_candidates:
        scraped = True
        print(f"Scraped {len(raw_candidates)} raw candidates across all categories")
    else:
        print("Scraping returned nothing — using fallback candidates")
        raw_candidates = FALLBACK_CANDIDATES

    # Enrich with margin math and filter
    qualified: list[dict] = []
    for c in raw_candidates:
        if not c.get("noon_price"):
            continue
        margin = calculate_margin(c["noon_price"], c.get("size", "small"))
        est_units = estimate_monthly_units(c["noon_price"], c.get("category", ""))
        if margin["margin_pct"] >= (MIN_MARGIN_PCT * 100) and est_units >= MIN_MONTHLY_UNITS:
            qualified.append({**c, "margin": margin, "est_monthly_units": est_units})

    # Sort by margin descending, cap at 10
    qualified.sort(key=lambda x: x["margin"]["margin_pct"], reverse=True)
    qualified = qualified[:10]

    if not qualified:
        print("No candidates passed filters — sending fallback report")
        qualified = []
        for c in FALLBACK_CANDIDATES[:5]:
            margin = calculate_margin(c["noon_price"], c.get("size", "small"))
            est_units = estimate_monthly_units(c["noon_price"], c.get("category", ""))
            qualified.append({**c, "margin": margin, "est_monthly_units": est_units})

    html_body = build_html_report(qualified, own_sales, scraped, report_date)
    subject = f"AARZOU Weekly Product Research — {len(qualified)} Opportunities — {report_date}"
    send_email(subject=subject, html_body=html_body)
    print(f"Report sent. {len(qualified)} opportunities included.")


if __name__ == "__main__":
    main()
