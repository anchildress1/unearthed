"""Generate fallback JSON files for each eGRID subregion with coal plants.

Run once from repo root:
    python -m scripts.generate_fallbacks
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.snowflake_client import query_mine_for_subregion

SUBREGIONS = [
    "AKGD", "AZNM", "CAMX", "ERCT", "FRCC", "MROE", "MROW", "NEWE",
    "NWPP", "RFCE", "RFCM", "RFCW", "RMPA", "SPNO", "SPSO", "SRMV",
    "SRMW", "SRSO", "SRTV", "SRVC",
]

FALLBACK_DIR = Path(__file__).parent.parent / "assets" / "fallback"


REQUIRED_FIELDS = [
    "mine", "mine_operator", "mine_county", "mine_state", "mine_type",
    "mine_coords", "plant", "plant_operator", "plant_coords", "tons", "tons_year",
]


def _validate(data: dict, subregion: str) -> list[str]:
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"{subregion}: missing field '{field}'")
    if not isinstance(data.get("mine_coords"), list) or len(data.get("mine_coords", [])) != 2:
        errors.append(f"{subregion}: mine_coords must be a 2-element list")
    if not isinstance(data.get("plant_coords"), list) or len(data.get("plant_coords", [])) != 2:
        errors.append(f"{subregion}: plant_coords must be a 2-element list")
    if data.get("tons", -1) < 0:
        errors.append(f"{subregion}: tons must be non-negative")
    return errors


def main() -> int:
    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    generated = 0

    for subregion in SUBREGIONS:
        print(f"Querying {subregion}...", end=" ")
        try:
            data = query_mine_for_subregion(subregion)
        except Exception as e:
            msg = f"{subregion}: Snowflake query failed — {e}"
            errors.append(msg)
            print(f"FAIL: {e}")
            continue

        if not data:
            print("no data (skipped)")
            continue

        validation_errors = _validate(data, subregion)
        if validation_errors:
            errors.extend(validation_errors)
            print(f"FAIL: {len(validation_errors)} validation error(s)")
            continue

        out = FALLBACK_DIR / f"{subregion}.json"
        out.write_text(json.dumps(data, indent=2))
        print(f"OK — {data['mine']}")
        generated += 1

    print(f"\n{generated}/{len(SUBREGIONS)} subregions generated.")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
