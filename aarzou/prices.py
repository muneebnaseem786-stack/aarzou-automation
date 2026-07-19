"""
`aarzou prices` - competitor pricing and Featured Offer (buy box) monitor.

Why this exists: on 20 Jun and again on 7 Jul, raising the Broom Holder to
AED 39.99 pushed it above Amazon's Competitive Price Threshold, forfeited the
Featured Offer, and took both campaigns dark for a full week before anyone
noticed. This surfaces that within a day.

Amazon returns the Competitive Price Threshold directly in the offers Summary,
so the ceiling is read live rather than remembered.
"""

from .config import PRODUCTS, SELLER_ID
from . import spapi


def _read_offers(client, asin):
    """
    Returns a dict describing the offer landscape for one ASIN, or {'error': str}.
    """
    try:
        resp = client.get_item_offers(asin, item_condition="New")
        payload = resp.payload or {}
    except Exception as exc:  # noqa: BLE001 - report per-ASIN, keep going
        return {"error": str(exc)}

    summary = payload.get("Summary") or {}
    offers = payload.get("Offers") or []

    def _amount(node):
        return None if not node else node.get("Amount")

    buybox = None
    for bb in summary.get("BuyBoxPrices") or []:
        amt = _amount(bb.get("LandedPrice"))
        if amt is not None:
            buybox = float(amt)
            break

    cpt = _amount(summary.get("CompetitivePriceThreshold"))
    cpt = float(cpt) if cpt is not None else None

    ours = None
    we_own_buybox = False
    we_are_featured = False
    competitors = []

    for offer in offers:
        amt = _amount(offer.get("ListingPrice"))
        if amt is None:
            continue
        landed = float(amt) + float(_amount(offer.get("Shipping")) or 0)
        if offer.get("SellerId") == SELLER_ID:
            ours = landed
            we_own_buybox = bool(offer.get("IsBuyBoxWinner"))
            we_are_featured = bool(offer.get("IsFeaturedMerchant"))
        else:
            competitors.append(landed)

    # If our seller id was not matched but a single offer holds the buy box and
    # the listing is ours, fall back to the buy-box winner rather than showing
    # nothing. Flagged so it is never silently wrong.
    fallback = False
    if ours is None and len(offers) == 1:
        only = offers[0]
        amt = _amount(only.get("ListingPrice"))
        if amt is not None and only.get("IsBuyBoxWinner"):
            ours = float(amt) + float(_amount(only.get("Shipping")) or 0)
            we_own_buybox = True
            we_are_featured = bool(only.get("IsFeaturedMerchant"))
            competitors = []
            fallback = True

    return {
        "ours": ours,
        "buybox": buybox,
        "cpt": cpt,
        "we_own_buybox": we_own_buybox,
        "we_are_featured": we_are_featured,
        "competitors": sorted(competitors),
        "offer_count": len(offers),
        "fallback": fallback,
    }


def run(args):
    spapi.load_env()

    asins = [a.upper() for a in args.asin] if args.asin else list(PRODUCTS)
    unknown = [a for a in asins if a not in PRODUCTS]
    if unknown:
        print(f"Unknown ASIN(s): {', '.join(unknown)}")
        return 2

    if not spapi.is_live():
        print("SP-API credentials not found - cannot fetch live pricing.\n")
        print("Missing: " + ", ".join(spapi.missing_credentials()))
        print("\nRun 'aarzou doctor' for setup instructions.")
        return 1

    client = spapi.products_client()

    print(f"{'PRODUCT':<28} {'OURS':>7} {'BUYBOX':>7} {'CPT':>7} {'COMP':>5} "
          f"{'LOWCOMP':>8}  {'FEATURED':<9} FLAG")
    print("-" * 100)

    alerts = []
    warnings = []

    for asin in asins:
        p = PRODUCTS[asin]
        d = _read_offers(client, asin)

        if "error" in d:
            print(f"{p.name[:27]:<28} {'ERROR':>7}  {d['error'][:52]}")
            alerts.append(f"{p.name}: API error - {d['error'][:120]}")
            continue

        ours, bb, cpt = d["ours"], d["buybox"], d["cpt"]
        comps = d["competitors"]

        flags = []

        # The failure mode that cost a week, twice.
        if ours is None:
            flags.append("NO LIVE OFFER")
            alerts.append(
                f"{p.name} ({asin}): we have no live offer - out of stock or suppressed."
            )
        elif not d["we_own_buybox"]:
            flags.append("LOST FEATURED OFFER")
            alerts.append(
                f"{p.name} ({asin}): NOT holding the Featured Offer at AED {ours:.2f}."
            )

        if cpt is not None and ours is not None and ours > cpt:
            flags.append(f"ABOVE CPT {cpt:.2f}")
            alerts.append(
                f"{p.name} ({asin}): AED {ours:.2f} exceeds the Competitive Price "
                f"Threshold of {cpt:.2f} - Featured Offer is at risk."
            )
        elif cpt is not None and ours is not None:
            head = cpt - ours
            if head < 2.00:
                flags.append(f"only {head:.2f} under CPT")

        if comps and ours is not None and ours > comps[0] * 1.10:
            flags.append(f"{((ours / comps[0]) - 1) * 100:.0f}% over lowest")

        if d["fallback"]:
            warnings.append(
                f"{p.name}: our seller id did not match; inferred our offer from the "
                f"sole buy-box winner. Verify SELLER_ID in config."
            )

        print(
            f"{p.name[:27]:<28} "
            f"{(f'{ours:.2f}' if ours is not None else '-'):>7} "
            f"{(f'{bb:.2f}' if bb is not None else 'none'):>7} "
            f"{(f'{cpt:.2f}' if cpt is not None else '-'):>7} "
            f"{len(comps):>5} "
            f"{(f'{comps[0]:.2f}' if comps else '-'):>8}  "
            f"{('YES' if d['we_own_buybox'] else 'NO'):<9} "
            f"{', '.join(flags) if flags else 'ok'}"
        )

    print("\nCPT = Amazon's Competitive Price Threshold, read live. Pricing above it")
    print("forfeits the Featured Offer, which stops ads AND organic sales.")
    print("COMP = number of competing offers. LOWCOMP = lowest competitor price.")

    if warnings:
        print("\nWARNINGS")
        for w in warnings:
            print(f"  ? {w}")

    if alerts:
        print("\n" + "=" * 100)
        print("ALERTS")
        for a in alerts:
            print(f"  ! {a}")
        return 1

    print("\nNo pricing alerts.")
    return 0
