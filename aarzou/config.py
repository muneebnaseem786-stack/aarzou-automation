"""
Product catalogue and unit economics for AARZOU.

Single source of truth for the CLI. Keep in sync with the brain files under
Documents/Claude/ventures/ and the memory project_*_ppc.md files.

COSTS
-----
Landed COGS below are USER-CONFIRMED (2026-07-10, recorded in the CT return
working papers). Do not replace them with figures from older PPC files - several
of those are stale (the AC Deflector ran on 20.00 for months against a real
28.00, and the Bidet on 77.74 against a real 55.00).

FBA fees are ESTIMATES, derived by decomposing documented gross profit figures.
They reconcile exactly with the confirmed COGS, but they are still inferred.
Run `aarzou fees` to replace them with real per-ASIN figures from the SP-API
Fees API; results cache to .fees_cache.json and are picked up automatically.
"""

import json
from pathlib import Path

MARKETPLACE_ID = "A2VIGQ35RCS4UG"  # Amazon UAE
REFERRAL_PCT = 0.15               # Amazon UAE, all categories we sell in

FEES_CACHE = Path(__file__).resolve().parent.parent / ".fees_cache.json"


def _load_fee_cache():
    if FEES_CACHE.exists():
        try:
            return json.loads(FEES_CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


_FEE_CACHE = _load_fee_cache()


class Product:
    """An Amazon SKU. All money in AED."""

    def __init__(self, asin, name, price, cogs, fba_fee_est, note=""):
        self.asin = asin
        self.name = name
        self.price = price
        self.cogs = cogs                  # landed, user-confirmed 2026-07-10
        self.fba_fee_est = fba_fee_est    # inferred; superseded by cache
        self.note = note

    # --- fees ---------------------------------------------------------
    @property
    def _cached(self):
        return _FEE_CACHE.get(self.asin, {})

    @property
    def fees_are_real(self):
        return bool(self._cached)

    @property
    def referral(self):
        c = self._cached.get("referral")
        return round(c if c is not None else self.price * REFERRAL_PCT, 2)

    @property
    def fba_fee(self):
        c = self._cached.get("fba")
        return round(c if c is not None else self.fba_fee_est, 2)

    # --- economics ----------------------------------------------------
    @property
    def gross_profit(self):
        return round(self.price - self.referral - self.fba_fee - self.cogs, 2)

    @property
    def be_acos(self):
        return self.gross_profit / self.price if self.price else 0.0

    def be_cvr(self, cpc):
        """CVR needed at a given CPC just to break even: CPC / GP."""
        gp = self.gross_profit
        return (cpc / gp) if gp > 0 else None

    def gp_at(self, price):
        """GP if price changed, holding flat costs constant."""
        return round(price - (price * REFERRAL_PCT) - self.fba_fee - self.cogs, 2)


PRODUCTS = {
    "B0C592JW6D": Product(
        "B0C592JW6D", "Travel Organizer (Beige)", 41.99, cogs=14.50, fba_fee_est=8.00,
        note="Price test 39.99 -> 41.99 on 18 Jul. Keep if >=16 PPC purchases/wk.",
    ),
    "B0C43HGC77": Product(
        "B0C43HGC77", "Travel Organizer (Grey)", 41.99, cogs=14.50, fba_fee_est=8.00,
        note="Price test 39.99 -> 41.99 on 18 Jul, moved with Beige.",
    ),
    "B09M69G8X7": Product(
        "B09M69G8X7", "Broom Holder (4-pack)", 34.99, cogs=9.00, fba_fee_est=9.00,
        note="PRICE CEILING 34.99 - two raises to 39.99 forfeited the Featured Offer.",
    ),
    "B0FBXBLF9Y": Product(
        "B0FBXBLF9Y", "Travel Portable Bidet", 99.99, cogs=55.00, fba_fee_est=9.24,
        note="Kept 99.99 post-restock. Revert trigger: <0.7 units/day over 2 weeks.",
    ),
    "B0F8W72SYT": Product(
        "B0F8W72SYT", "Lavalier Microphone", 69.99, cogs=40.00, fba_fee_est=6.26,
        note="PPC paused. Branded relaunch ~23 Jul.",
    ),
}

# Reorder thresholds, units (from the existing daily monitor)
REORDER_THRESHOLDS = {
    "B0F8W72SYT": 10,
    "B09M69G8X7": 8,
    "B0FBXBLF9Y": 8,
    "B0C592JW6D": 5,
    "B0C43HGC77": 5,
}

# Amazon Competitive Price Thresholds observed in practice. Exceeding these has
# forfeited the Featured Offer (buy box).
KNOWN_PRICE_CEILINGS = {
    "B09M69G8X7": 34.99,
}


# --- Noon -------------------------------------------------------------
# Noon fees differ per category and are NOT a flat 15%. Where a value is None
# it is genuinely unknown - do not guess it.
class NoonProduct:
    def __init__(self, partner_sku, sku_id, name, price, cogs,
                 referral_pct=None, fulfilment=None, note=""):
        self.partner_sku = partner_sku
        self.sku_id = sku_id
        self.name = name
        self.price = price
        self.cogs = cogs
        self.referral_pct = referral_pct
        self.fulfilment = fulfilment
        self.note = note

    @property
    def gross_profit(self):
        if self.referral_pct is None or self.fulfilment is None:
            return None
        return round(
            self.price - (self.price * self.referral_pct) - self.fulfilment - self.cogs, 2
        )

    @property
    def be_acos(self):
        gp = self.gross_profit
        return (gp / self.price) if gp is not None and self.price else None

    def cash_recovery(self, price=None):
        """Cash back per unit ignoring sunk COGS - the clearance metric."""
        if self.referral_pct is None or self.fulfilment is None:
            return None
        p = self.price if price is None else price
        return round(p - (p * self.referral_pct) - self.fulfilment, 2)


NOON_PRODUCTS = {
    "Mop Holder": NoonProduct(
        "Mop Holder", "ZF736A4B7BAFA7C0FEACCZ-1", "Broom Holder (4-pack)",
        price=34.99, cogs=9.00, referral_pct=0.157, fulfilment=9.50,
        note="Reviews stuck at 3 for 3 cycles - the binding constraint.",
    ),
    "Bidet Set": NoonProduct(
        "Bidet Set", "Z0AE232493494ACB1DF25Z-1", "Travel Portable Bidet",
        price=99.99, cogs=55.00, referral_pct=None, fulfilment=None,
        note="Best PPC line in the portfolio. Noon fee split not yet confirmed.",
    ),
    "AC Deflector": NoonProduct(
        "AC Deflector", "ZFBFF053F29D5ECFEAB44Z-1", "AC Deflector",
        price=49.99, cogs=28.00, referral_pct=0.137, fulfilment=12.50,
        note="CLEARANCE by 31 Aug. COGS is 28.00, NOT the 20.00 used in reviews to 18 Jul.",
    ),
    "Microphone": NoonProduct(
        "Microphone", None, "Lavalier Microphone",
        price=None, cogs=40.00, referral_pct=None, fulfilment=None,
        note="Price and Noon fee split not confirmed.",
    ),
}
