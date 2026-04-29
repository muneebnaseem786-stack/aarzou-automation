"""
Noon UAE data layer — stub.
Real integration requires API credentials from seller.noon.com → Settings → API credentials.
Returns mock/empty data until credentials are configured.
"""

import os

import pandas as pd


def is_live() -> bool:
    return bool(os.environ.get("NOON_API_KEY"))


PRODUCTS = {
    # Populate once Noon SKUs are known and API credentials are obtained
}


def get_inventory() -> pd.DataFrame:
    """Returns inventory DataFrame. Empty until Noon credentials configured."""
    if not is_live():
        return pd.DataFrame()

    # TODO: implement Noon Commercial API call
    # Endpoint: https://api.noon.partners/seller/v2/inventory
    # Auth: Bearer token via NOON_API_KEY env var
    return pd.DataFrame()


def get_sales_7d() -> pd.DataFrame:
    """Returns 7-day sales DataFrame. Empty until Noon credentials configured."""
    if not is_live():
        return pd.DataFrame()

    # TODO: implement Noon orders API
    return pd.DataFrame()
