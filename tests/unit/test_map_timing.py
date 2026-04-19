"""Unit tests verifying map reveal timing constants."""

import re
from pathlib import Path

MAP_JS = (Path(__file__).parent.parent.parent / "static" / "js" / "map.js").read_text()


def _extract_const(name: str) -> int:
    """Extract a numeric const from map.js source."""
    match = re.search(rf"const {name}\s*=\s*(\d+)", MAP_JS)
    assert match, f"Could not find const {name} in map.js"
    return int(match.group(1))


FLY_DURATION = _extract_const("FLY_DURATION")
HOLD_DURATION = _extract_const("HOLD_DURATION")
LOAD_TIMEOUT = _extract_const("MAP_LOAD_TIMEOUT_MS")


class TestMapTimingSpec:
    def test_fly_duration_is_positive(self):
        assert FLY_DURATION > 0

    def test_hold_duration_allows_user_to_read(self):
        assert HOLD_DURATION >= 2000, "Hold too short for user to register location"

    def test_fly_is_reasonable(self):
        assert FLY_DURATION >= 1000, "Fly too fast for animation to be visible"

    def test_load_timeout_is_generous(self):
        assert LOAD_TIMEOUT >= 10000
