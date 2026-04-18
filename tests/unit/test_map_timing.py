"""Unit tests verifying map reveal timing stays within the 8-second spec."""

import re
from pathlib import Path

MAP_JS = (Path(__file__).parent.parent.parent / "static" / "js" / "map.js").read_text()


def _extract_const(name: str) -> int:
    """Extract a numeric const from map.js source."""
    match = re.search(rf"const {name}\s*=\s*(\d+)", MAP_JS)
    assert match, f"Could not find const {name} in map.js"
    return int(match.group(1))


STEP_DURATION = _extract_const("STEP_DURATION_MS")
PAUSE_BETWEEN = _extract_const("PAUSE_BETWEEN_MS")
LOAD_TIMEOUT = _extract_const("MAP_LOAD_TIMEOUT_MS")

# The reveal has 4 delay(stepDelay) awaits where stepDelay = STEP + PAUSE
TOTAL_SEQUENCE_MS = 4 * (STEP_DURATION + PAUSE_BETWEEN)


class TestMapTimingSpec:
    """PRD requires total map reveal sequence <= 8 seconds."""

    def test_total_sequence_under_8_seconds(self):
        assert TOTAL_SEQUENCE_MS <= 8000, (
            f"Map reveal is {TOTAL_SEQUENCE_MS}ms, exceeds 8000ms spec"
        )

    def test_step_duration_is_positive(self):
        assert STEP_DURATION > 0

    def test_pause_is_positive(self):
        assert PAUSE_BETWEEN > 0

    def test_step_is_reasonable(self):
        # Each step should be long enough for the flyTo to be visible
        assert STEP_DURATION >= 1000, "Step too fast for animation to be visible"

    def test_load_timeout_exceeds_sequence(self):
        # Timeout must be longer than the full sequence
        assert LOAD_TIMEOUT > TOTAL_SEQUENCE_MS

    def test_four_steps_in_sequence(self):
        # Verify the code has exactly 4 delay awaits
        assert MAP_JS.count("await delay(stepDelay)") == 4
