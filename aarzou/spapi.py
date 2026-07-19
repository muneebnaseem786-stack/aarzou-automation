"""
SP-API access layer for the AARZOU CLI.

Credentials come from the environment. Locally that means a .env file at the
repo root (already gitignored); in GitHub Actions it means repository secrets.

Required:
    AMAZON_CLIENT_ID
    AMAZON_CLIENT_SECRET
    AMAZON_REFRESH_TOKEN
"""

import os
from pathlib import Path

REQUIRED_VARS = ("AMAZON_CLIENT_ID", "AMAZON_CLIENT_SECRET", "AMAZON_REFRESH_TOKEN")


def load_env():
    """
    Minimal .env loader - avoids adding python-dotenv as a dependency.
    Existing environment variables always win.
    """
    for parent in (Path(__file__).resolve().parent.parent, Path.cwd()):
        env_path = parent / ".env"
        if not env_path.exists():
            continue
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        break


def missing_credentials():
    """Returns the list of required env vars that are absent or empty."""
    return [v for v in REQUIRED_VARS if not os.environ.get(v)]


def is_live():
    return not missing_credentials()


def credentials():
    return {
        "lwa_app_id": os.environ["AMAZON_CLIENT_ID"],
        "lwa_client_secret": os.environ["AMAZON_CLIENT_SECRET"],
        "refresh_token": os.environ["AMAZON_REFRESH_TOKEN"],
    }


def products_client():
    """
    Returns an sp_api Products client for the UAE marketplace.
    Raises RuntimeError with a readable message if anything is missing.
    """
    gaps = missing_credentials()
    if gaps:
        raise RuntimeError(
            "Missing SP-API credentials: " + ", ".join(gaps) +
            "\nAdd them to a .env file at the repo root (see 'aarzou doctor')."
        )
    try:
        from sp_api.api import Products
        from sp_api.base import Marketplaces
    except ImportError as exc:
        raise RuntimeError(
            "python-amazon-sp-api is not installed. Run: pip install python-amazon-sp-api"
        ) from exc

    return Products(credentials=credentials(), marketplace=Marketplaces.AE)
