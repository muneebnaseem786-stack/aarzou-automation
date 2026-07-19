"""
`aarzou prices` - competitor pricing and Featured Offer (buy box) monitor.

Why this exists: on 20 Jun and again on 7 Jul, raising the Broom Holder to
AED 39.99 pushed it above Amazon's Competitive Price Threshold, forfeited the
Featured Offer, and took both campaigns dark for a full week before anyone
noticed. This command surfaces that within a day.
"""

from .config import PRODUCTS, KNOWN_PRICE_CEILINGS
from . import spapi


def _offers_for(client, asin):
    """
    Pull the offer listing for one ASIN.
    Returns (buybox_price, our_price, we_own_buybox, competitor_prices, error).
    """
    try:
        resp = client.get_item_offers(asin, item_condition="New")
        payload = resp.payload or {}
    except Exception as exc:  # noqa: BLE001 - surface any API failure per-ASIN
        return None, None, None, [], str(exc)

    summary = payload.get("Summary", {}) or {}
    offers = payload.get("Offers", []) or []

    buybox_price = None
    for bb in summary.get("BuyBoxPrices", []) or []:
        amount = (bb.get("LandedPrice") or {}).get("Amount")
        if amount is not None:
            buybox_price = float(amount)
            break

    our_price = None
    we_own_buybox = False
    competitor_prices = []

    for offer in offers:
        amount = (offer.get("ListingPrice") or {}).get("Amount")
        shipping = (offer.get("Shipping") or {}).get("Amount") or 0
        if amount is None:
            continue
        landed = float(amount) + float(shipping)
        if offer.get("MyOffer"):
            our_price = landed
            if offer.get("IsBuyBoxWinner"):
                we_own_buybox = True
        else:
            competitor_prices.append(landed)

    return buybox_price, our_price, we_own_buybox, sorted(competitor_prices), None


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

    print(f"{'PRODUCT':<32} {'OURS':>8} {'BUYBOX':>8} {'LOWEST':>8}  {'BUYBOX?':<9} FLAG")
    print("-" * 92)

    alerts = []

    for asin in asins:
        p = PRODUCTS[asin]
        bb, ours, we_own, comps, err = _offers_for(client, asin)

        if err:
            print(f"{p.name[:31]:<32} {'-':>8} {'-':>8} {'-':>8}  {'ERROR':<9} {err[:28]}")
            alerts.append(f"{p.name}: API error - {err}")
            continue

        ours_disp = f"{ours:.2f}" if ours is not None else "-"
        bb_disp = f"{bb:.2f}" if bb is not None else "none"
        low_disp = f"{comps[0]:.2f}" if comps else "-"
        own_disp = "YES" if we_own else "NO"

        flags = []

        # The failure mode that cost a week, twice.
        if ours is not None and not we_own:
            flags.append("LOST FEATURED OFFER")
            alerts.append(
                f"{p.name} ({asin}): we do NOT hold the Featured Offer at AED {ours:.2f}."
            )

        if bb is None and ours is not None:
            flags.append("NO BUYBOX ON LISTING")
            alerts.append(f"{p.name} ({asin}): no Featured Offer exists on the listing.")

        ceiling = KNOWN_PRICE_CEILINGS.get(asin)
        if ceiling and ours is not None and ours > ceiling:
            flags.append(f"ABOVE KNOWN CEILING {ceiling:.2f}")
            alerts.append(
                f"{p.name} ({asin}): AED {ours:.2f} is above the known "
                f"Competitive Price Threshold of {ceiling:.2f}."
            )

        if comps and ours is not None and ours > comps[0] * 1.10:
            flags.append(f"{((ours / comps[0]) - 1) * 100:.0f}% OVER LOWEST")

        print(
            f"{p.name[:31]:<32} {ours_disp:>8} {bb_disp:>8} {low_disp:>8}  "
            f"{own_disp:<9} {', '.join(flags) if flags else 'ok'}"
        )

    print()
    for asin in asins:
        p = PRODUCTS[asin]
        print(
            f"{p.name[:31]:<32} GP {p.gross_profit:>6.2f}  "
            f"BE-ACoS {p.be_acos * 100:>5.1f}%  "
            f"(referral {p.referral:.2f} + flat cost {p.flat_cost:.2f})"
        )

    if alerts:
        print("\n" + "=" * 92)
        print("ALERTS")
        for a in alerts:
            print(f"  ! {a}")
        return 1

    print("\nNo pricing alerts.")
    return 0
