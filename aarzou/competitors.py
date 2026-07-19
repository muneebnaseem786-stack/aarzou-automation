"""
`aarzou competitors` - track named competitor ASINs and their prices over time.

Amazon's offers API on OUR OWN asin returns offers on our listing, which are
mostly dropshippers reselling our product, NOT the competitive set. Real
competitive intelligence means tracking specific competing PRODUCTS, so the
competitor list is curated by hand.

    aarzou competitors add B0XXXXXXXX --for B09M69G8X7 --label "Generic 4-pack"
    aarzou competitors                  check all tracked competitors
    aarzou competitors --for B09M69G8X7 check one of our SKUs' rivals
    aarzou competitors remove B0XXXXXXXX
    aarzou competitors history B0XXXXXXXX

Every check appends to price history, so movements are visible over time.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import PRODUCTS
from . import spapi
from .reviews import _fetch as fetch_reviews, REVIEWS_FILE

COMPETITORS_FILE = Path(__file__).resolve().parent.parent / "competitors.json"


def _load():
    if COMPETITORS_FILE.exists():
        try:
            return json.loads(COMPETITORS_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            print(f"WARNING: {COMPETITORS_FILE.name} is unreadable, starting fresh.")
    return {"competitors": {}, "history": {}}


def _save(data):
    COMPETITORS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _fetch(client, asin):
    """Returns (price, buybox_price, offer_count, title_hint, error)."""
    try:
        resp = client.get_item_offers(asin, item_condition="New")
        payload = resp.payload or {}
    except Exception as exc:  # noqa: BLE001
        return None, None, None, None, str(exc)

    summary = payload.get("Summary") or {}
    buybox = None
    for bb in summary.get("BuyBoxPrices") or []:
        amt = (bb.get("LandedPrice") or {}).get("Amount")
        if amt is not None:
            buybox = float(amt)
            break

    prices = []
    for offer in payload.get("Offers") or []:
        amt = (offer.get("ListingPrice") or {}).get("Amount")
        if amt is None:
            continue
        prices.append(float(amt) + float((offer.get("Shipping") or {}).get("Amount") or 0))

    total = 0
    for n in summary.get("NumberOfOffers") or []:
        total += int(n.get("OfferCount") or 0)

    return (min(prices) if prices else None), buybox, (total or len(prices)), None, None


def cmd_add(args):
    data = _load()
    asin = args.asin.upper()
    target = args.for_asin.upper() if args.for_asin else None
    if target and target not in PRODUCTS:
        print(f"Unknown SKU: {target}. Known: {', '.join(PRODUCTS)}")
        return 2
    data["competitors"][asin] = {
        "label": args.label or asin,
        "for": target,
        "added": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    _save(data)
    against = f" (rival to {PRODUCTS[target].name})" if target else ""
    print(f"Tracking {asin} as '{args.label or asin}'{against}.")
    print(f"{len(data['competitors'])} competitor(s) tracked. Run 'aarzou competitors'.")
    return 0


def cmd_remove(args):
    data = _load()
    asin = args.asin.upper()
    if asin not in data["competitors"]:
        print(f"{asin} is not being tracked.")
        return 1
    label = data["competitors"].pop(asin).get("label", asin)
    _save(data)
    print(f"Stopped tracking {asin} ('{label}'). Price history retained.")
    return 0


def cmd_history(args):
    data = _load()
    asin = args.asin.upper()
    hist = (data.get("history") or {}).get(asin) or []
    if not hist:
        print(f"No price history for {asin} yet.")
        return 1
    label = (data["competitors"].get(asin) or {}).get("label", asin)
    print(f"Price history - {label} ({asin})\n")
    print(f"{'DATE':<12} {'PRICE':>8} {'CHANGE':>9}")
    print("-" * 32)
    prev = None
    for row in hist:
        price = row.get("price")
        if price is None:
            print(f"{row['date']:<12} {'-':>8} {'-':>9}")
            continue
        delta = f"{price - prev:+.2f}" if prev is not None else "-"
        print(f"{row['date']:<12} {price:>8.2f} {delta:>9}")
        prev = price
    return 0


def _our_reviews(asin):
    """Latest known review count for one of our own ASINs, if recorded."""
    if not REVIEWS_FILE.exists():
        return None
    try:
        hist = json.loads(REVIEWS_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    rows = hist.get(asin) or []
    for r in reversed(rows):
        if r.get("count") is not None:
            return r["count"]
    return None


def cmd_check(args):
    data = _load()
    tracked = data.get("competitors") or {}
    if not tracked:
        print("No competitors tracked yet.\n")
        print("Add them with:")
        print("  aarzou competitors add B0XXXXXXXX --for B09M69G8X7 --label \"Rival name\"")
        print("\nUse rival PRODUCT listings, not offers on your own ASIN - those are")
        print("mostly dropshippers reselling your product, not the competitive set.")
        return 0

    spapi.load_env()
    if not spapi.is_live():
        print("SP-API credentials not found. Run 'aarzou doctor'.")
        return 1

    only_for = args.for_asin.upper() if args.for_asin else None
    client = spapi.products_client()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history = data.setdefault("history", {})

    groups = {}
    for asin, meta in tracked.items():
        if only_for and meta.get("for") != only_for:
            continue
        groups.setdefault(meta.get("for"), []).append((asin, meta))

    if not groups:
        print(f"No competitors tracked for {only_for}.")
        return 0

    failures = 0
    for our_asin, rivals in sorted(groups.items(), key=lambda kv: str(kv[0])):
        ours = PRODUCTS.get(our_asin)
        if ours:
            ourrev = _our_reviews(our_asin)
            rev_txt = f", {ourrev} reviews" if ourrev is not None else ""
            print(f"\n{ours.name} - ours AED {ours.price:.2f}{rev_txt}")
        else:
            print("\nUnassigned competitors")
        print(f"  {'COMPETITOR':<26} {'PRICE':>8} {'VS OURS':>8} {'REVIEWS':>8} "
              f"{'RATING':>7} {'OFFERS':>7}  MOVE")
        print("  " + "-" * 88)

        for asin, meta in sorted(rivals, key=lambda r: r[1].get("label", "")):
            price, buybox, offers, _t, err = _fetch(client, asin)
            rcount, rrating, rerr = fetch_reviews(asin)
            time.sleep(2.0)

            if err:
                failures += 1
                print(f"  {meta.get('label', asin)[:25]:<26} {'ERROR':>8}  {err[:40]}")
                continue

            rows = history.setdefault(asin, [])
            prev = next((r["price"] for r in reversed(rows)
                         if r.get("price") is not None), None)
            entry = {"date": today, "price": price, "buybox": buybox,
                     "reviews": rcount, "rating": rrating}
            if not rows or rows[-1]["date"] != today:
                rows.append(entry)
            else:
                rows[-1] = entry

            vs = "-"
            if price is not None and ours:
                vs = f"{(price / ours.price - 1) * 100:+.0f}%"
            move = "-"
            if price is not None and prev is not None:
                d = price - prev
                move = "unchanged" if abs(d) < 0.01 else f"{d:+.2f}"

            print(f"  {meta.get('label', asin)[:25]:<26} "
                  f"{(f'{price:.2f}' if price is not None else '-'):>8} "
                  f"{vs:>8} "
                  f"{(rcount if rcount is not None else '-'):>8} "
                  f"{(f'{rrating:.1f}' if rrating else '-'):>7} "
                  f"{(offers if offers is not None else '-'):>7}  {move}")

    _save(data)
    total = sum(len(v) for v in groups.values())
    print(f"\nChecked {total} competitor(s). History saved to {COMPETITORS_FILE.name}.")
    print("VS OURS is the rival's price relative to our current list price.")
    print("MOVE is the price change since the previous check.")
    return 1 if failures else 0
