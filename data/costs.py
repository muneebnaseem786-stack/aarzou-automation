"""
Landed cost store — reads/writes a local JSON file.
User enters landed cost per unit (product + shipping + customs) via the dashboard.
"""

import json
from pathlib import Path

_COSTS_FILE = Path(__file__).parent / "product_costs.json"

# Placeholder defaults — user should overwrite via dashboard
_DEFAULTS = {
    "B0F8W72SYT": 45.0,
    "B09M69G8X7": 12.0,
    "B0FBXBLF9Y": 32.0,
    "B0C592JW6D": 22.0,
    "B0C43HGC77": 22.0,
}


def load() -> dict:
    if _COSTS_FILE.exists():
        with open(_COSTS_FILE) as f:
            return json.load(f)
    return dict(_DEFAULTS)


def save(costs: dict) -> None:
    with open(_COSTS_FILE, "w") as f:
        json.dump(costs, f, indent=2)
