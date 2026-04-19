"""Unit tests verifying map.js animation pattern."""

from pathlib import Path

MAP_JS = (Path(__file__).parent.parent.parent / "static" / "js" / "map.js").read_text()


class TestMapAnimationPattern:
    def test_uses_fit_bounds(self):
        assert "fitBounds" in MAP_JS

    def test_uses_pan_to(self):
        assert "panTo" in MAP_JS

    def test_waits_for_idle(self):
        assert "waitForIdle" in MAP_JS

    def test_does_not_call_move_camera(self):
        """moveCamera requires mapId — we don't call it."""
        assert ".moveCamera(" not in MAP_JS

    def test_flow_line_is_slow(self):
        assert "0.1" in MAP_JS

    def test_uses_geodesic_lines(self):
        assert "geodesic: true" in MAP_JS

    def test_uses_hybrid_map_type(self):
        assert "hybrid" in MAP_JS
