"""
`aarzou review-pack` - assemble everything needed for the weekly review.

Replaces the manual routine of downloading dozens of CSV exports from the
Amazon and Noon consoles. Runs every read-only check in sequence and prints
one consolidated report.

    aarzou review-pack              full pack, 7-day window
    aarzou review-pack --days 14    wider window
    aarzou review-pack --quick      skip competitors and reviews (no scraping)

PPC sections appear once the Amazon Ads API is approved.
"""

import io
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone


def _section(title):
    print("\n" + "=" * 92)
    print(f"  {title}")
    print("=" * 92)


def _run(fn, args, label):
    """Run a command, capture its output, report failures without aborting."""
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            code = fn(args)
        print(buf.getvalue().rstrip())
        return code
    except Exception as exc:  # noqa: BLE001
        out = buf.getvalue().rstrip()
        if out:
            print(out)
        print(f"\n  [{label} failed: {type(exc).__name__}: {str(exc)[:120]}]")
        return 1


class _Args:
    """Lightweight stand-in for argparse namespaces."""

    def __init__(self, **kw):
        self.asin = []
        self.days = 7
        self.for_asin = None
        for k, v in kw.items():
            setattr(self, k, v)


def run(args):
    from . import commands, prices as prices_mod
    from .config import PRODUCTS

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("=" * 92)
    print(f"  AARZOU WEEKLY REVIEW PACK - {stamp}")
    print(f"  Window: last {args.days} days | {len(PRODUCTS)} Amazon SKUs")
    print("=" * 92)

    failures = []

    _section("1. UNIT ECONOMICS")
    if _run(commands.cmd_econ, _Args(), "econ"):
        failures.append("econ")

    _section("2. INVENTORY AND VELOCITY")
    if _run(commands.cmd_inventory, _Args(days=args.days), "inventory"):
        failures.append("inventory")

    _section("3. SALES")
    if _run(commands.cmd_sales, _Args(days=args.days), "sales"):
        failures.append("sales")

    _section("4. PRICING AND FEATURED OFFER")
    if _run(prices_mod.run, _Args(), "prices"):
        failures.append("prices")

    if not args.quick:
        _section("5. REVIEWS")
        from . import reviews as reviews_mod
        if _run(reviews_mod.run, _Args(), "reviews"):
            failures.append("reviews")

        _section("6. COMPETITORS")
        from . import competitors as comp_mod
        if _run(comp_mod.cmd_check, _Args(), "competitors"):
            failures.append("competitors")
    else:
        print("\n(skipped reviews and competitors: --quick)")

    _section("7. ADVERTISING")
    print("  Amazon Ads API not yet available (applied 19 Jul 2026).")
    print("  Until approval, PPC reports still come from console CSV exports.")
    print("  Noon PPC has no API and stays manual regardless.")

    print("\n" + "=" * 92)
    if failures:
        print(f"  PACK COMPLETE WITH {len(failures)} FAILED SECTION(S): "
              f"{', '.join(failures)}")
        print("  Treat missing sections as unknown, not as zero.")
    else:
        print("  PACK COMPLETE - all sections succeeded.")
    print("=" * 92)
    return 1 if failures else 0
