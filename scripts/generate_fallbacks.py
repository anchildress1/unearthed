"""Generate fallback JSON files for each eGRID subregion with coal plants.

Run once from repo root:
    python -m scripts.generate_fallbacks
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.snowflake_client import query_mine_for_subregion

SUBREGIONS = [
    "AKGD", "AZNM", "CAMX", "ERCT", "FRCC", "MROE", "MROW", "NEWE",
    "NWPP", "RFCE", "RFCM", "RFCW", "RMPA", "SPNO", "SPSO", "SRMV",
    "SRMW", "SRSO", "SRTV", "SRVC",
]

FALLBACK_DIR = Path(__file__).parent.parent / "assets" / "fallback"


def main():
    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    for subregion in SUBREGIONS:
        print(f"Querying {subregion}...", end=" ")
        try:
            data = query_mine_for_subregion(subregion)
            if data:
                out = FALLBACK_DIR / f"{subregion}.json"
                out.write_text(json.dumps(data, indent=2, default=str))
                print(f"OK — {data['mine']}")
            else:
                print("no data")
        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
