"""
aarzou - command line interface for AARZOU marketplace operations.

Goal: run the business from the terminal instead of the Amazon and Noon
web consoles, so decisions can be made against live data rather than
manually downloaded exports.

Available now (Amazon SP-API):
    aarzou doctor                 credentials and setup check
    aarzou econ [ASIN ...]        GP, break-even ACoS, break-even CVR
    aarzou fees [ASIN ...]        real referral + FBA fees, cached for econ
    aarzou inventory [--days N]   stock, velocity, days of cover, reorder alerts
    aarzou sales [--days N]       units, revenue, GP, prices actually transacted
    aarzou prices [ASIN ...]      competitor pricing + Featured Offer monitor
    aarzou noon                   Noon unit economics (API client pending)

Planned once the Amazon Ads API is approved (applied 19 Jul 2026):
    aarzou ppc week               pull all campaign reports, run doctrine checks
    aarzou drift                  diff live campaign settings vs intended
    aarzou review-pack            everything, formatted for the weekly review
"""

import argparse
import sys

from . import spapi, commands
from .config import PRODUCTS, NOON_PRODUCTS


def cmd_doctor(args):
    spapi.load_env()
    print("AARZOU CLI - environment check\n")

    gaps = spapi.missing_credentials()
    if gaps:
        print("  SP-API             NOT CONFIGURED")
        for g in gaps:
            print(f"                     missing {g}")
    else:
        print("  SP-API             configured")

    try:
        import sp_api  # noqa: F401
        print("  sp_api library     installed")
    except ImportError:
        print("  sp_api library     MISSING -> pip install python-amazon-sp-api")

    real = sum(1 for p in PRODUCTS.values() if p.fees_are_real)
    print(f"  Amazon products    {len(PRODUCTS)} ASINs "
          f"({real} with real fees, {len(PRODUCTS) - real} estimated)")
    print(f"  Noon products      {len(NOON_PRODUCTS)} SKUs (API client not wired)")
    print("  Ads API            applied 19 Jul 2026, awaiting approval email")

    if gaps:
        print(
            "\nTo configure SP-API, create a .env file at the repo root:\n"
            "\n"
            "    AMAZON_CLIENT_ID=...\n"
            "    AMAZON_CLIENT_SECRET=...\n"
            "    AMAZON_REFRESH_TOKEN=...\n"
            "\n"
            ".env is gitignored. The same three values are in GitHub Secrets."
        )
        return 1

    print("\nReady. Try 'aarzou fees' first so econ uses real fee figures.")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="aarzou",
        description="AARZOU marketplace operations CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run 'aarzou doctor' first to check setup.",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("doctor", help="check credentials and setup")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("econ", help="GP, break-even ACoS and break-even CVR")
    p.add_argument("asin", nargs="*", help="ASINs (default: all)")
    p.set_defaults(func=commands.cmd_econ)

    p = sub.add_parser("fees", help="fetch real referral + FBA fees from SP-API")
    p.add_argument("asin", nargs="*", help="ASINs (default: all)")
    p.set_defaults(func=commands.cmd_fees)

    p = sub.add_parser("inventory", help="stock, velocity, cover and reorder alerts")
    p.add_argument("--days", type=int, default=7, help="velocity window (default 7)")
    p.set_defaults(func=commands.cmd_inventory)

    p = sub.add_parser("sales", help="units, revenue, GP and transacted prices")
    p.add_argument("--days", type=int, default=7, help="window (default 7)")
    p.set_defaults(func=commands.cmd_sales)

    p = sub.add_parser("prices", help="competitor pricing + Featured Offer monitor")
    p.add_argument("asin", nargs="*", help="ASINs (default: all)")
    p.set_defaults(func=lambda a: __import__(
        "aarzou.prices", fromlist=["run"]).run(a))

    p = sub.add_parser("noon", help="Noon unit economics")
    p.set_defaults(func=commands.cmd_noon)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
