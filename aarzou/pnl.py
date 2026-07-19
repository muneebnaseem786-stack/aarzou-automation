"""
`aarzou pnl` - periodic profit and loss across ALL sales, not just ad-attributed.

Why this exists: the weekly PPC reviews only ever see ad-attributed revenue, so
organic sales - usually the majority - are invisible. A campaign can look
marginal while the SKU is comfortably profitable, or vice versa. This shows the
whole picture.

    aarzou pnl                  last 30 days
    aarzou pnl --days 7         last week
    aarzou pnl --days 90        quarter
    aarzou pnl --ads 140.24     include a known ad spend figure

Ad spend is NOT yet automatic - the Amazon Ads API application is pending. Pass
it with --ads from the campaign reports, or leave it out and the report will say
so rather than pretending contribution is profit.
"""

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .config import PRODUCTS, MARKETPLACE_ID
from . import spapi

BAR = "-" * 100



def _throttled(fn, *a, **kw):
    """
    Call an SP-API method, backing off on throttle. Orders allows roughly
    0.5 rps on order items, so bursts must be paced or the whole run dies.
    """
    delay = 2.0
    for attempt in range(6):
        try:
            return fn(*a, **kw), None
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "Quota" not in msg and "Throttled" not in msg and "429" not in msg:
                return None, exc
            time.sleep(delay)
            delay = min(delay * 2, 30)
    return None, RuntimeError("still throttled after 6 attempts")


def _collect(days):
    """
    Pull every order in the window. Returns (rows, error) where rows is
    {asin: {"units", "revenue", "orders", "prices"}}.
    """
    try:
        from sp_api.api import Orders
        from sp_api.base import Marketplaces
    except ImportError:
        return None, "python-amazon-sp-api not installed"

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    agg = defaultdict(lambda: {"units": 0, "revenue": 0.0, "orders": 0, "prices": set()})

    try:
        api = Orders(credentials=spapi.credentials(), marketplace=Marketplaces.AE)
        resp, exc = _throttled(api.get_orders, CreatedAfter=since,
                               MarketplaceIds=[MARKETPLACE_ID])
        if exc:
            return None, f"{type(exc).__name__}: {str(exc)[:160]}"
        payload = resp.payload or {}
        orders = payload.get("Orders", []) or []
        token = payload.get("NextToken")

        # Follow pagination so longer windows are complete, not truncated.
        while token:
            resp, exc = _throttled(api.get_orders, NextToken=token,
                                   MarketplaceIds=[MARKETPLACE_ID])
            if exc:
                break
            payload = resp.payload or {}
            orders.extend(payload.get("Orders", []) or [])
            token = payload.get("NextToken")

        live = [o for o in orders
                if o.get("OrderStatus") not in ("Canceled", "Pending")]
        print(f"  fetching items for {len(live)} orders "
              f"(paced for API limits, ~{len(live) * 2 // 60 + 1} min)...")

        for n, order in enumerate(live, 1):
            items, exc = _throttled(api.get_order_items, order.get("AmazonOrderId"))
            if exc:
                continue
            time.sleep(2.0)
            if n % 25 == 0:
                print(f"    {n}/{len(live)}")
            for it in (items.payload or {}).get("OrderItems", []) or []:
                asin = it.get("ASIN")
                if asin not in PRODUCTS:
                    continue
                qty = int(it.get("QuantityOrdered", 0))
                amt = float((it.get("ItemPrice") or {}).get("Amount", 0) or 0)
                a = agg[asin]
                a["units"] += qty
                a["revenue"] += amt
                a["orders"] += 1
                if qty:
                    a["prices"].add(round(amt / qty, 2))
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {str(exc)[:160]}"

    return agg, None


def run(args):
    if not spapi.is_live():
        spapi.load_env()
    if not spapi.is_live():
        print("SP-API credentials not found. Run 'aarzou doctor'.")
        return 1

    days = args.days
    agg, err = _collect(days)
    if err:
        print(f"Could not build P&L: {err}")
        return 1

    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d %b")
    end = datetime.now(timezone.utc).strftime("%d %b %Y")
    print(f"AMAZON P&L - ALL SALES (organic + advertised)")
    print(f"{start} to {end}  |  {days} days\n")

    print(f"{'PRODUCT':<26} {'UNITS':>6} {'REVENUE':>10} {'REFERRAL':>9} "
          f"{'FBA':>8} {'COGS':>9} {'GROSS':>10} {'MARGIN':>7}")
    print(BAR)

    tot = defaultdict(float)
    any_estimated = False

    for asin, p in PRODUCTS.items():
        d = agg.get(asin)
        units = d["units"] if d else 0
        revenue = d["revenue"] if d else 0.0
        if not p.fees_are_real:
            any_estimated = True

        referral = units * p.referral
        fba = units * p.fba_fee
        cogs = units * p.cogs
        gross = revenue - referral - fba - cogs
        margin = (gross / revenue * 100) if revenue else 0.0

        tot["units"] += units
        tot["revenue"] += revenue
        tot["referral"] += referral
        tot["fba"] += fba
        tot["cogs"] += cogs
        tot["gross"] += gross

        print(f"{p.name[:25]:<26} {units:>6} {revenue:>10.2f} {referral:>9.2f} "
              f"{fba:>8.2f} {cogs:>9.2f} {gross:>10.2f} {margin:>6.1f}%")

    print(BAR)
    tot_margin = (tot["gross"] / tot["revenue"] * 100) if tot["revenue"] else 0.0
    print(f"{'TOTAL':<26} {int(tot['units']):>6} {tot['revenue']:>10.2f} "
          f"{tot['referral']:>9.2f} {tot['fba']:>8.2f} {tot['cogs']:>9.2f} "
          f"{tot['gross']:>10.2f} {tot_margin:>6.1f}%")

    # --- below the gross line ---
    print(f"\n{'CONTRIBUTION WATERFALL':<40}")
    print(BAR)
    print(f"  {'Revenue (all channels)':<44} {tot['revenue']:>12.2f}")
    print(f"  {'less Amazon referral fees':<44} {-tot['referral']:>12.2f}")
    print(f"  {'less FBA fulfilment':<44} {-tot['fba']:>12.2f}")
    print(f"  {'less landed COGS':<44} {-tot['cogs']:>12.2f}")
    print(f"  {'= GROSS PROFIT':<44} {tot['gross']:>12.2f}")

    ads = getattr(args, "ads", None)
    if ads is not None:
        net = tot["gross"] - ads
        print(f"  {'less advertising spend':<44} {-ads:>12.2f}")
        print(BAR)
        print(f"  {'= NET CONTRIBUTION':<44} {net:>12.2f}")
        if tot["revenue"]:
            print(f"  {'net margin':<44} {net / tot['revenue'] * 100:>11.1f}%")
            print(f"  {'ad spend as % of revenue (TACoS)':<44} "
                  f"{ads / tot['revenue'] * 100:>11.1f}%")
    else:
        print(BAR)
        print("  ADVERTISING SPEND NOT INCLUDED - this is gross profit, not profit.")
        print("  The Amazon Ads API is still pending, so ad spend cannot be pulled")
        print("  automatically. Re-run with --ads <amount> from the campaign reports.")

    print(f"\n  Daily gross profit: {tot['gross'] / days:>.2f}   "
          f"Daily revenue: {tot['revenue'] / days:>.2f}")

    if any_estimated:
        print("\n  NOTE: some fees are estimated. Run 'aarzou fees' for real figures.")

    print("\n  Not included: storage fees, inbound freight, returns/refunds,")
    print("  removal fees, and any off-platform overheads. This is a unit-economics")
    print("  P&L, not a statutory one.")
    print("\n  Noon is not included - its API is not yet connected.")
    return 0
