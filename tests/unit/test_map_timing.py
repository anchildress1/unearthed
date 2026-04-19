"""Unit tests verifying map.js uses moveCamera animation pattern."""

from pathlib import Path

MAP_JS = (Path(__file__).parent.parent.parent / "static" / "js" / "map.js").read_text()


class TestMapAnimationPattern:
    def test_uses_move_camera(self):
        assert "moveCamera" in MAP_JS

    def test_uses_request_animation_frame(self):
        assert "requestAnimationFrame" in MAP_JS

    def test_has_easing_function(self):
        assert "easeInOutCubic" in MAP_JS

    def test_has_lerp(self):
        assert "lerp" in MAP_JS

    def test_flow_line_is_slow(self):
        # offset increment should be <= 0.2 per tick
        assert "0.15" in MAP_JS

    def test_uses_geodesic_lines(self):
        assert "geodesic: true" in MAP_JS
