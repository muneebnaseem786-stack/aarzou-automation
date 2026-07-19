"""
`aarzou reviews` - track review counts and ratings per SKU over time.

Reviews are the documented bottleneck across the portfolio: Noon Broom Holder
stuck at 3 for three review cycles, AC Deflector at 0 for three months, Mic at
7 for six sessions, Amazon Bidet gating its auto relaunch at 15. Until now these
numbers were asked for by hand every week and were often unconfirmed.

SP-API does not expose review counts, so this reads the public product page.
Amazon actively varies its markup, so parsing can break - when it does the
command says so rather than reporting a wrong number.
"""

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import PRODUCTS

REVIEWS_FILE = Path(__file__).resolve().parent.parent / "reviews_history.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Ordered most-specific first. The generic "N ratings" pattern was removed:
# it matched unrelated numbers elsewhere on the page and produced confidently
# wrong counts (Broom Holder read as 3 when the real figure is 159).
COUNT_PATTERNS = [
    r'data-hook="total-review-count"[^>]*>\s*([\d,]+)',
    r'id="acrCustomerReviewText"[^>]*>\s*\(?([\d,]+)',
    r'acrCustomerReviewText[^>]*>\s*\(?([\d,]+)',
]
RATING_PATTERNS = [
    r'id="acrPopover"[^>]*title="([\d.]+) out of 5',
    r'a-icon-alt"[^>]*>\s*([\d.]+) out of 5',
    r'([\d.]+)\s*out of\s*5\s*stars',
]


def _load():
    if REVIEWS_FILE.exists():
        try:
            return json.loads(REVIEWS_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _fetch(asin):
    """Returns (count, rating, error)."""
    url = f"https://www.amazon.ae/dp/{asin}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "en-AE,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return None, None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, None, type(e).__name__

    if "captcha" in html.lower() or "api-services-support@amazon.com" in html:
        return None, None, "blocked (captcha)"

    count = rating = None
    for pat in COUNT_PATTERNS:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            try:
                count = int(m.group(1).replace(",", ""))
                break
            except ValueError:
                continue
    for pat in RATING_PATTERNS:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            try:
                rating = float(m.group(1))
                break
            except ValueError:
                continue

    if count is None:
        return None, rating, "could not parse review count"
    return count, rating, None


def run(args):
    asins = [a.upper() for a in args.asin] if args.asin else list(PRODUCTS)
    unknown = [a for a in asins if a not in PRODUCTS]
    if unknown:
        print(f"Unknown ASIN(s): {', '.join(unknown)}")
        return 2

    hist = _load()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"{'PRODUCT':<30} {'REVIEWS':>8} {'RATING':>7} {'CHANGE':>9}  NOTE")
    print("-" * 88)

    failures = 0
    for i, asin in enumerate(asins):
        p = PRODUCTS[asin]
        count, rating, err = _fetch(asin)
        if i < len(asins) - 1:
            time.sleep(2.5)  # be gentle

        rows = hist.setdefault(asin, [])
        prev = next((r["count"] for r in reversed(rows) if r.get("count") is not None), None)

        if err:
            failures += 1
            print(f"{p.name[:29]:<30} {'-':>8} {'-':>7} {'-':>9}  {err}")
            continue

        if not rows or rows[-1]["date"] != today:
            rows.append({"date": today, "count": count, "rating": rating})
        else:
            rows[-1] = {"date": today, "count": count, "rating": rating}

        change = "-"
        if prev is not None:
            d = count - prev
            change = "no change" if d == 0 else f"{d:+d}"
        note = ""
        if prev is not None and count == prev:
            note = "STALLED since last check"
        print(f"{p.name[:29]:<30} {count:>8} "
              f"{(f'{rating:.1f}' if rating else '-'):>7} {change:>9}  {note}")

    REVIEWS_FILE.write_text(json.dumps(hist, indent=2), encoding="utf-8")
    print(f"\nHistory saved to {REVIEWS_FILE.name}.")
    if failures:
        print(f"{failures} lookup(s) failed. Amazon varies its page markup and rate-limits")
        print("scrapers; a failure means no number was read, never a wrong number.")
        return 1
    return 0
