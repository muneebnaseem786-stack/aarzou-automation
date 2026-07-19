"""
Command implementations for the aarzou CLI.

Live data comes from SP-API. Every command degrades with a clear message when
credentials are absent rather than silently returning mock numbers - a wrong
number presented confidently is worse than no number.
"""

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import spapi
from .config import (
    PRODUCTS, NOON_PRODUCTS, REORDER_THRESHOLDS, KNOWN_PRICE_CEILINGS,
    MARKETPLACE_ID, FEES_CACHE,
)

BAR = "-" * 92


def _resolve(asin_args):
    """Validate ASIN arguments; return (asins, error_code_or_None)."""
    asins = [a.upper() for a in asin_args] if asin_args else list(PRODUCTS)
    unknown = [a for a in asins if a not in PRODUCTS]
    if unknown:
        print(f"Unknown ASIN(s): {', '.join(unknown)}")
        print(f"Known: {', '.join(PRODUCTS)}")
        return None, 2
    return asins, None


def _require_live():
    spapi.load_env()
    if spapi.is_live():
        return True
    print("SP-API credentials not found.\n")
    print("Missing: " + ", ".join(spapi.missing_credentials()))
    print("\nRun 'aarzou doctor' for setup instructions.")
    return False


# ---------------------------------------------------------------- econ
def cmd_econ(args):
    asins, err = _resolve(args.asin)
    if err:
        return err

    any_estimated = False
    print(f"{'PRODUCT':<30} {'PRICE':>7} {'REF':>6} {'FBA':>6} {'COGS':>6} "
          f"{'GP':>7} {'BE-ACoS':>8}  FEES")
    print(BAR)
    for asin in asins:
        p = PRODUCTS[asin]
        src = "real" if p.fees_are_real else "est"
        if not p.fees_are_real:
            any_estimated = True
        print(f"{p.name[:29]:<30} {p.price:>7.2f} {p.referral:>6.2f} {p.fba_fee:>6.2f} "
              f"{p.cogs:>6.2f} {p.gross_profit:>7.2f} {p.be_acos * 100:>7.1f}%  {src}")

    print(f"\n{'PRODUCT':<30} BE-CVR required at CPC")
    print(BAR)
    for asin in asins:
        p = PRODUCTS[asin]
        cells = []
        for cpc in (1.00, 1.50, 2.00, 2.50, 3.00):
            v = p.be_cvr(cpc)
            cells.append(f"{cpc:.2f}:{v * 100:>4.0f}%" if v else f"{cpc:.2f}: n/a")
        print(f"{p.name[:29]:<30} {'  '.join(cells)}")

    print("\nBE-CVR is the conversion rate a placement needs at that CPC just to break")
    print("even. If a placement's actual CVR is below it, the margin cannot afford it.")

    if any_estimated:
        print("\nNOTE: FBA fees marked 'est' are inferred, not fetched.")
        print("      Run 'aarzou fees' to replace them with real SP-API figures.")

    for asin in asins:
        if PRODUCTS[asin].note:
            print(f"\n  {PRODUCTS[asin].name}: {PRODUCTS[asin].note}")
    return 0


# ---------------------------------------------------------------- fees
def cmd_fees(args):
    if not _require_live():
        return 1
    asins, err = _resolve(args.asin)
    if err:
        return err

    try:
        from sp_api.api import ProductFees
        from sp_api.base import Marketplaces
    except ImportError:
        print("python-amazon-sp-api not installed. Run: pip install python-amazon-sp-api")
        return 1

    api = ProductFees(credentials=spapi.credentials(), marketplace=Marketplaces.AE)
    cache = {}
    if FEES_CACHE.exists():
        try:
            cache = json.loads(FEES_CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cache = {}

    print(f"{'PRODUCT':<30} {'PRICE':>7} {'REFERRAL':>9} {'FBA':>8} {'TOTAL':>8}")
    print(BAR)

    failures = 0
    for asin in asins:
        p = PRODUCTS[asin]
        try:
            resp = None
            last_exc = None
            for attempt in range(4):
                try:
                    resp = api.get_product_fees_estimate_for_asin(
                        asin, price=p.price, currency="AED", is_fba=True,
                    )
                    break
                except Exception as e:  # noqa: BLE001
                    last_exc = e
                    if "Quota" not in str(e) and "429" not in str(e):
                        raise
                    time.sleep(2 ** attempt)  # 1s, 2s, 4s, 8s
            if resp is None:
                raise last_exc
            payload = resp.payload or {}
            result = payload.get("FeesEstimateResult", payload)
            estimate = result.get("FeesEstimate", {}) or {}
            details = estimate.get("FeeDetailList", []) or []

            referral = fba = None
            for d in details:
                ftype = d.get("FeeType", "")
                amount = (d.get("FeeAmount") or {}).get("Amount")
                if amount is None:
                    continue
                if ftype == "ReferralFee":
                    referral = float(amount)
                elif ftype in ("FBAFees", "FulfillmentFee", "VariableClosingFee"):
                    fba = (fba or 0) + float(amount)

            total = (estimate.get("TotalFeesEstimate") or {}).get("Amount")
            entry = {"price": p.price, "fetched": datetime.now(timezone.utc).isoformat()}
            if referral is not None:
                entry["referral"] = round(referral, 2)
            if fba is not None:
                entry["fba"] = round(fba, 2)
            cache[asin] = entry

            time.sleep(1.2)
            print(f"{p.name[:29]:<30} {p.price:>7.2f} "
                  f"{(f'{referral:.2f}' if referral is not None else '-'):>9} "
                  f"{(f'{fba:.2f}' if fba is not None else '-'):>8} "
                  f"{(f'{float(total):.2f}' if total is not None else '-'):>8}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"{p.name[:29]:<30} {p.price:>7.2f} {'ERROR':>9}  {str(exc)[:34]}")

    if cache:
        FEES_CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        print(f"\nCached to {FEES_CACHE.name}. 'aarzou econ' now uses these figures.")
        print("Fees are price-dependent - re-run after any price change.")
    return 1 if failures else 0


# ----------------------------------------------------------- inventory
def cmd_inventory(args):
    if not _require_live():
        return 1

    try:
        from sp_api.api import Inventories
        from sp_api.base import Marketplaces
    except ImportError:
        print("python-amazon-sp-api not installed.")
        return 1

    stock = defaultdict(int)
    try:
        api = Inventories(credentials=spapi.credentials(), marketplace=Marketplaces.AE)
        resp = api.get_inventory_summary_marketplace(
            details=True, granularityType="Marketplace", granularityId=MARKETPLACE_ID,
        )
        for item in (resp.payload or {}).get("inventorySummaries", []):
            asin = item.get("asin")
            if asin in PRODUCTS:
                qty = (item.get("inventoryDetails") or {}).get("fulfillableQuantity", 0)
                stock[asin] += qty
    except Exception as exc:  # noqa: BLE001
        print(f"Inventory API error: {exc}")
        return 1

    units = _units_sold(args.days)

    print(f"Amazon FBA inventory and velocity, last {args.days} days\n")
    print(f"{'PRODUCT':<30} {'STOCK':>6} {'SOLD':>6} {'/DAY':>6} {'COVER':>7}  STATUS")
    print(BAR)
    alerts = []
    for asin in PRODUCTS:
        p = PRODUCTS[asin]
        qty = stock.get(asin, 0)
        sold = units.get(asin, 0) if units is not None else None
        per_day = (sold / args.days) if sold is not None else None
        cover = (qty / per_day) if per_day else None
        thresh = REORDER_THRESHOLDS.get(asin, 0)

        status = "ok"
        if qty == 0:
            status = "OUT OF STOCK"
            alerts.append(f"{p.name}: OUT OF STOCK")
        elif qty <= thresh:
            status = f"REORDER (<={thresh})"
            alerts.append(f"{p.name}: {qty} units, at or below reorder point {thresh}")
        elif cover is not None and cover < 21:
            status = "under 3wk cover"
            alerts.append(f"{p.name}: only {cover:.0f} days of cover")

        print(f"{p.name[:29]:<30} {qty:>6} "
              f"{(sold if sold is not None else '-'):>6} "
              f"{(f'{per_day:.2f}' if per_day else '-'):>6} "
              f"{(f'{cover:.0f}d' if cover else '-'):>7}  {status}")

    if alerts:
        print("\nALERTS")
        for a in alerts:
            print(f"  ! {a}")
        return 1
    print("\nNo inventory alerts.")
    return 0


def _units_sold(days):
    """Units sold per ASIN over the window, from the Orders API. None on failure."""
    try:
        from sp_api.api import Orders
        from sp_api.base import Marketplaces
    except ImportError:
        return None

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    units = defaultdict(int)
    try:
        api = Orders(credentials=spapi.credentials(), marketplace=Marketplaces.AE)
        resp = api.get_orders(CreatedAfter=since, MarketplaceIds=[MARKETPLACE_ID])
        orders = (resp.payload or {}).get("Orders", []) or []
        for order in orders:
            if order.get("OrderStatus") in ("Canceled", "Pending"):
                continue
            oid = order.get("AmazonOrderId")
            if not oid:
                continue
            items = api.get_order_items(oid)
            for it in (items.payload or {}).get("OrderItems", []) or []:
                asin = it.get("ASIN")
                if asin in PRODUCTS:
                    units[asin] += int(it.get("QuantityOrdered", 0))
    except Exception:  # noqa: BLE001
        return None
    return units


# --------------------------------------------------------------- sales
def cmd_sales(args):
    if not _require_live():
        return 1

    try:
        from sp_api.api import Orders
        from sp_api.base import Marketplaces
    except ImportError:
        print("python-amazon-sp-api not installed.")
        return 1

    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    units = defaultdict(int)
    revenue = defaultdict(float)
    prices = defaultdict(set)

    try:
        api = Orders(credentials=spapi.credentials(), marketplace=Marketplaces.AE)
        resp = api.get_orders(CreatedAfter=since, MarketplaceIds=[MARKETPLACE_ID])
        orders = (resp.payload or {}).get("Orders", []) or []
        for order in orders:
            if order.get("OrderStatus") in ("Canceled", "Pending"):
                continue
            items = api.get_order_items(order.get("AmazonOrderId"))
            for it in (items.payload or {}).get("OrderItems", []) or []:
                asin = it.get("ASIN")
                if asin not in PRODUCTS:
                    continue
                qty = int(it.get("QuantityOrdered", 0))
                amt = float((it.get("ItemPrice") or {}).get("Amount", 0) or 0)
                units[asin] += qty
                revenue[asin] += amt
                if qty:
                    prices[asin].add(round(amt / qty, 2))
    except Exception as exc:  # noqa: BLE001
        print(f"Orders API error: {exc}")
        return 1

    print(f"Amazon sales, last {args.days} days\n")
    print(f"{'PRODUCT':<30} {'UNITS':>6} {'REVENUE':>9} {'/DAY':>6} {'GP':>9}  PRICES SOLD AT")
    print(BAR)
    tot_u = tot_r = tot_gp = 0.0
    for asin in PRODUCTS:
        p = PRODUCTS[asin]
        u, r = units.get(asin, 0), revenue.get(asin, 0.0)
        gp = u * p.gross_profit
        tot_u += u
        tot_r += r
        tot_gp += gp
        seen = ", ".join(f"{x:.2f}" for x in sorted(prices.get(asin, []))) or "-"
        print(f"{p.name[:29]:<30} {u:>6} {r:>9.2f} {u / args.days:>6.2f} {gp:>9.2f}  {seen}")
    print(BAR)
    print(f"{'TOTAL':<30} {int(tot_u):>6} {tot_r:>9.2f} "
          f"{tot_u / args.days:>6.2f} {tot_gp:>9.2f}")
    print("\nGP uses configured costs. Run 'aarzou fees' first for real fee figures.")
    print("PRICES SOLD AT reveals promo/deal prices actually transacted.")
    return 0


# ---------------------------------------------------------------- noon
def cmd_noon(args):
    print("Noon unit economics (API client not yet wired - figures from config)\n")
    print(f"{'PRODUCT':<26} {'PRICE':>7} {'COGS':>6} {'GP':>8} {'BE-ACoS':>8} {'CASH':>7}")
    print(BAR)
    for key, n in NOON_PRODUCTS.items():
        gp = n.gross_profit
        be = n.be_acos
        cash = n.cash_recovery()
        print(f"{n.name[:25]:<26} "
              f"{(f'{n.price:.2f}' if n.price else '-'):>7} {n.cogs:>6.2f} "
              f"{(f'{gp:.2f}' if gp is not None else 'n/a'):>8} "
              f"{(f'{be * 100:.1f}%' if be is not None else 'n/a'):>8} "
              f"{(f'{cash:.2f}' if cash is not None else 'n/a'):>7}")
    print("\nCASH = cash recovered per unit ignoring sunk COGS (the clearance metric).")
    print("'n/a' means the Noon fee split is genuinely unknown - not guessed.")
    for n in NOON_PRODUCTS.values():
        if n.note:
            print(f"\n  {n.name}: {n.note}")
    print("\nNoon API is blocked: NOON_CREDENTIALS_JSON was never added to GitHub")
    print("Secrets, and key 93a0d12a (exposed 1 May) still needs rotating.")
    return 0
