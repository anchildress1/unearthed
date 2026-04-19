"""Unit tests verifying map reveal timing constants."""

import re
from pathlib import Path

MAP_JS = (Path(__file__).parent.parent.parent / "static" / "js" / "map.js").read_text()


def _extract_const(name: str) -> int:
    """Extract a numeric const from map.js source."""
    match = re.search(rf"const {name}\s*=\s*(\d+)", MAP_JS)
    assert match, f"Could not find const {name} in map.js"
    return int(match.group(1))


HOLD_SHORT = _extract_const("HOLD_SHORT")
HOLD_LONG = _extract_const("HOLD_LONG")
HOLD_MORBID = _extract_const("HOLD_MORBID")
ZOOM_STEP_MS = _extract_const("ZOOM_STEP_MS")
LOAD_TIMEOUT = _extract_const("MAP_LOAD_TIMEOUT_MS")


class TestMapTimingSpec:
    def test_hold_short_is_readable(self):
        assert HOLD_SHORT >= 1500, "Short hold too brief to register"

    def test_hold_long_lets_user_orient(self):
        assert HOLD_LONG >= 3000, "Long hold too brief to orient"

    def test_hold_morbid_is_deliberate(self):
        assert HOLD_MORBID >= 4000, "Morbid hold should be uncomfortably long"

    def test_zoom_step_is_smooth(self):
        assert ZOOM_STEP_MS >= 80, "Zoom steps too fast — will feel jarring"

    def test_load_timeout_is_generous(self):
        assert LOAD_TIMEOUT >= 10000
