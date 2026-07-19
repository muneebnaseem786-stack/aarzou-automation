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
    """
    Run a command and capture its output.

    Returns "ok", "alerts", or "failed". Commands return exit code 1 both for
    genuine failures AND for successful runs that raised alerts (an out-of-stock
    SKU, say). Only an exception counts as a failure - an alert means the check
    worked and found something worth knowing.
    """
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            code = fn(args)
        print(buf.getvalue().rstrip())
        return "alerts" if code else "ok"
    except Exception as exc:  # noqa: BLE001
        out = buf.getvalue().rstrip()
        if out:
            print(out)
        print(f"\n  [{label} FAILED: {type(exc).__name__}: {str(exc)[:160]}]")
        return "failed"


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

    failures, alerted = [], []

    def record(name, status):
        if status == "failed":
            failures.append(name)
        elif status == "alerts":
            alerted.append(name)

    _section("1. UNIT ECONOMICS")
    record("econ", _run(commands.cmd_econ, _Args(), "econ"))

    _section("2. INVENTORY AND VELOCITY")
    record("inventory", _run(commands.cmd_inventory, _Args(days=args.days), "inventory"))

    _section("3. SALES")
    record("sales", _run(commands.cmd_sales, _Args(days=args.days), "sales"))

    _section("4. PRICING AND FEATURED OFFER")
    record("prices", _run(prices_mod.run, _Args(), "prices"))

    if not args.quick:
        _section("5. REVIEWS")
        from . import reviews as reviews_mod
        record("reviews", _run(reviews_mod.run, _Args(), "reviews"))

        _section("6. COMPETITORS")
        from . import competitors as comp_mod
        record("competitors", _run(comp_mod.cmd_check, _Args(), "competitors"))
    else:
        print("\n(skipped reviews and competitors: --quick)")

    _section("7. ADVERTISING")
    print("  Amazon Ads API not yet available (applied 19 Jul 2026).")
    print("  Until approval, PPC reports still come from console CSV exports.")
    print("  Noon PPC has no API and stays manual regardless.")

    print("\n" + "=" * 92)
    if failures:
        print(f"  {len(failures)} SECTION(S) FAILED: {', '.join(failures)}")
        print("  Treat those as unknown, not as zero.")
    if alerted:
        print(f"  SECTIONS RAISING ALERTS: {', '.join(alerted)} - see above.")
    if not failures and not alerted:
        print("  PACK COMPLETE - all sections clean, no alerts.")
    elif not failures:
        print("  PACK COMPLETE - all sections ran.")
    print("=" * 92)
    return 1 if failures else 0
