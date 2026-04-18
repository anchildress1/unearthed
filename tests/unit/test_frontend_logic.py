"""Unit tests for frontend logic validated server-side.

Tests the correctness of algorithms and data structures used in the
frontend JS modules by re-implementing the logic in Python. This
ensures the ray-casting PIP algorithm, state-to-subregion mapping,
and ticker math are correct.
"""

import json
from pathlib import Path

import pytest

# --- Point-in-Polygon (mirrors geo.js ray-casting algorithm) ---


def point_in_ring(x, y, ring):
    """Ray-casting algorithm for a single ring. Mirrors geo.js."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < ((xj - xi) * (y - yi)) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_in_polygon_rings(x, y, rings):
    """Test point against polygon with holes. Mirrors geo.js."""
    inside = point_in_ring(x, y, rings[0])
    for h in range(1, len(rings)):
        if point_in_ring(x, y, rings[h]):
            inside = not inside
    return inside


def find_subregion(lat, lon, geojson):
    """Find eGRID subregion for a point. Mirrors geo.js."""
    for feature in geojson["features"]:
        geom_type = feature["geometry"]["type"]
        coords = feature["geometry"]["coordinates"]
        if geom_type == "MultiPolygon":
            for polygon in coords:
                if point_in_polygon_rings(lon, lat, polygon):
                    return feature["properties"]["Subregion"]
        elif geom_type == "Polygon":
            if point_in_polygon_rings(lon, lat, coords):
                return feature["properties"]["Subregion"]
    return None


# State-to-subregion mapping (must match geo.js exactly)
STATE_TO_SUBREGION = {
    "AL": "SRSO",
    "AK": "AKGD",
    "AZ": "AZNM",
    "AR": "SRMV",
    "CA": "CAMX",
    "CO": "RMPA",
    "CT": "NEWE",
    "DE": "RFCE",
    "FL": "FRCC",
    "GA": "SRSO",
    "HI": "HIMS",
    "ID": "NWPP",
    "IL": "SRMW",
    "IN": "RFCW",
    "IA": "MROW",
    "KS": "SPNO",
    "KY": "SRTV",
    "LA": "SRMV",
    "ME": "NEWE",
    "MD": "RFCE",
    "MA": "NEWE",
    "MI": "RFCM",
    "MN": "MROW",
    "MS": "SRMV",
    "MO": "SRMW",
    "MT": "NWPP",
    "NE": "MROW",
    "NV": "NWPP",
    "NH": "NEWE",
    "NJ": "RFCE",
    "NM": "AZNM",
    "NY": "NYUP",
    "NC": "SRVC",
    "ND": "MROW",
    "OH": "RFCW",
    "OK": "SPSO",
    "OR": "NWPP",
    "PA": "RFCE",
    "RI": "NEWE",
    "SC": "SRVC",
    "SD": "MROW",
    "TN": "SRTV",
    "TX": "ERCT",
    "UT": "NWPP",
    "VT": "NEWE",
    "VA": "SRVC",
    "WA": "NWPP",
    "WV": "SRVC",
    "WI": "MROE",
    "WY": "RMPA",
    "DC": "RFCE",
}

COAL_SUBREGIONS = {
    "AKGD",
    "AZNM",
    "CAMX",
    "ERCT",
    "FRCC",
    "MROE",
    "MROW",
    "NWPP",
    "RFCE",
    "RFCM",
    "RFCW",
    "RMPA",
    "SPNO",
    "SPSO",
    "SRMV",
    "SRMW",
    "SRSO",
    "SRTV",
    "SRVC",
}

SECONDS_IN_YEAR = 365.25 * 24 * 60 * 60


@pytest.fixture(scope="module")
def geojson():
    path = Path(__file__).parent.parent.parent / "static" / "data" / "egrid_subregions.geojson"
    return json.loads(path.read_text())


# --- PIP Tests ---


class TestPointInRing:
    def test_point_inside_simple_square(self):
        square = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]
        assert point_in_ring(2, 2, square) is True

    def test_point_outside_simple_square(self):
        square = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]
        assert point_in_ring(5, 5, square) is False

    def test_point_on_edge(self):
        # Edge cases are implementation-defined; just ensure no crash
        square = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]
        point_in_ring(0, 2, square)

    def test_point_at_vertex(self):
        square = [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]
        point_in_ring(0, 0, square)

    def test_triangle(self):
        tri = [[0, 0], [5, 0], [2.5, 5], [0, 0]]
        assert point_in_ring(2.5, 2, tri) is True
        assert point_in_ring(10, 10, tri) is False

    def test_empty_ring_returns_false(self):
        assert point_in_ring(0, 0, []) is False

    def test_negative_coordinates(self):
        square = [[-10, -10], [10, -10], [10, 10], [-10, 10], [-10, -10]]
        assert point_in_ring(0, 0, square) is True
        assert point_in_ring(-20, 0, square) is False


class TestPointInPolygonRings:
    def test_point_in_outer_ring(self):
        rings = [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]
        assert point_in_polygon_rings(5, 5, rings) is True

    def test_point_in_hole(self):
        rings = [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[3, 3], [7, 3], [7, 7], [3, 7], [3, 3]],
        ]
        assert point_in_polygon_rings(5, 5, rings) is False

    def test_point_between_hole_and_outer(self):
        rings = [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[3, 3], [7, 3], [7, 7], [3, 7], [3, 3]],
        ]
        assert point_in_polygon_rings(1, 1, rings) is True


class TestFindSubregion:
    """Test the PIP algorithm against real eGRID GeoJSON."""

    def test_columbia_sc_is_srvc(self, geojson):
        result = find_subregion(34.0, -81.0, geojson)
        assert result == "SRVC"

    def test_houston_tx_is_erct(self, geojson):
        result = find_subregion(29.76, -95.37, geojson)
        assert result == "ERCT"

    def test_chicago_il_is_rfcw(self, geojson):
        result = find_subregion(41.88, -87.63, geojson)
        assert result == "RFCW"

    def test_denver_co_is_rmpa(self, geojson):
        result = find_subregion(39.74, -104.99, geojson)
        assert result == "RMPA"

    def test_outside_us_returns_none(self, geojson):
        result = find_subregion(51.5, -0.12, geojson)  # London
        assert result is None

    def test_ocean_returns_none(self, geojson):
        result = find_subregion(30.0, -60.0, geojson)  # Atlantic Ocean
        assert result is None

    def test_anchorage_returns_akgd(self, geojson):
        result = find_subregion(61.2, -149.9, geojson)
        assert result == "AKGD"

    def test_orlando_is_frcc(self, geojson):
        result = find_subregion(28.54, -81.38, geojson)
        assert result == "FRCC"

    def test_portland_or_is_nwpp(self, geojson):
        result = find_subregion(45.52, -122.68, geojson)
        assert result == "NWPP"

    def test_north_pole_returns_none(self, geojson):
        result = find_subregion(90.0, 0.0, geojson)
        assert result is None


# --- State-to-Subregion Mapping ---


class TestStateToSubregion:
    def test_all_50_states_plus_dc_covered(self):
        assert len(STATE_TO_SUBREGION) == 51

    def test_west_virginia_maps_to_srvc(self):
        assert STATE_TO_SUBREGION["WV"] == "SRVC"

    def test_texas_maps_to_erct(self):
        assert STATE_TO_SUBREGION["TX"] == "ERCT"

    def test_wyoming_maps_to_rmpa(self):
        assert STATE_TO_SUBREGION["WY"] == "RMPA"

    def test_ohio_maps_to_rfcw(self):
        assert STATE_TO_SUBREGION["OH"] == "RFCW"

    def test_all_values_are_valid_subregions(self, geojson):
        geojson_subregions = {f["properties"]["Subregion"] for f in geojson["features"]}
        for state, subregion in STATE_TO_SUBREGION.items():
            assert subregion in geojson_subregions, (
                f"State {state} maps to {subregion} which is not in GeoJSON"
            )

    def test_unknown_state_not_in_mapping(self):
        assert "ZZ" not in STATE_TO_SUBREGION

    def test_dc_is_included(self):
        assert STATE_TO_SUBREGION["DC"] == "RFCE"


class TestCoalSubregions:
    def test_fallback_files_exist_for_all_coal_subregions(self):
        fallback_dir = Path(__file__).parent.parent.parent / "assets" / "fallback"
        for sr in COAL_SUBREGIONS:
            assert (fallback_dir / f"{sr}.json").exists(), f"Missing fallback for {sr}"

    def test_coal_subregion_count(self):
        assert len(COAL_SUBREGIONS) == 19

    def test_srvc_is_coal(self):
        assert "SRVC" in COAL_SUBREGIONS

    def test_newe_is_not_coal(self):
        assert "NEWE" not in COAL_SUBREGIONS

    def test_hims_is_not_coal(self):
        assert "HIMS" not in COAL_SUBREGIONS


# --- Ticker Math ---


class TestTickerMath:
    def test_tons_per_second_calculation(self):
        annual_tons = 1_000_000
        tps = annual_tons / SECONDS_IN_YEAR
        assert tps == pytest.approx(0.03169, rel=1e-3)

    def test_zero_tonnage_returns_zero(self):
        assert 0 / SECONDS_IN_YEAR == 0.0

    def test_large_tonnage(self):
        annual_tons = 50_000_000
        tps = annual_tons / SECONDS_IN_YEAR
        assert tps == pytest.approx(1.585, rel=1e-2)

    def test_ticker_after_60_seconds(self):
        annual_tons = 1_247_001.0
        tps = annual_tons / SECONDS_IN_YEAR
        after_60 = tps * 60
        assert after_60 > 0
        assert after_60 == pytest.approx(2.371, rel=1e-2)

    def test_seconds_in_year_constant(self):
        assert SECONDS_IN_YEAR == pytest.approx(31_557_600, rel=1e-6)


# --- Share URL Validation ---


class TestShareUrlValidation:
    """Validates the subregion ID pattern used for share URLs."""

    def test_valid_subregion_patterns(self):
        import re

        pattern = re.compile(r"^[A-Za-z0-9]{2,10}$")
        valid = ["SRVC", "ERCT", "RFCW", "AKGD", "srvc", "AB"]
        for v in valid:
            assert pattern.match(v), f"Should match: {v}"

    def test_invalid_subregion_patterns(self):
        import re

        pattern = re.compile(r"^[A-Za-z0-9]{2,10}$")
        invalid = ["", "A", "../etc", "SRVC;DROP", "ABCDEFGHIJK", "SR VC", "SR\nVC"]
        for v in invalid:
            assert not pattern.match(v), f"Should not match: {v}"


# --- Fallback JSON Structure ---


class TestFallbackJsonStructure:
    """Verify all fallback JSON files have the required fields."""

    def test_all_fallback_files_valid(self):
        fallback_dir = Path(__file__).parent.parent.parent / "assets" / "fallback"
        required_keys = {
            "mine",
            "mine_operator",
            "mine_county",
            "mine_state",
            "mine_type",
            "mine_coords",
            "plant",
            "plant_operator",
            "plant_coords",
            "tons",
            "tons_year",
        }
        for f in fallback_dir.glob("*.json"):
            data = json.loads(f.read_text())
            missing = required_keys - set(data.keys())
            assert not missing, f"{f.name} missing keys: {missing}"

    def test_all_fallback_coords_are_valid(self):
        fallback_dir = Path(__file__).parent.parent.parent / "assets" / "fallback"
        for f in fallback_dir.glob("*.json"):
            data = json.loads(f.read_text())
            lat, lon = data["mine_coords"]
            assert -90 <= lat <= 90, f"{f.name}: bad mine lat {lat}"
            assert -180 <= lon <= 180, f"{f.name}: bad mine lon {lon}"
            lat, lon = data["plant_coords"]
            assert -90 <= lat <= 90, f"{f.name}: bad plant lat {lat}"
            assert -180 <= lon <= 180, f"{f.name}: bad plant lon {lon}"

    def test_all_fallback_tons_are_positive(self):
        fallback_dir = Path(__file__).parent.parent.parent / "assets" / "fallback"
        for f in fallback_dir.glob("*.json"):
            data = json.loads(f.read_text())
            assert data["tons"] > 0, f"{f.name}: tons should be positive"

    def test_all_fallback_mine_types_valid(self):
        fallback_dir = Path(__file__).parent.parent.parent / "assets" / "fallback"
        valid_types = {"Surface", "Underground"}
        for f in fallback_dir.glob("*.json"):
            data = json.loads(f.read_text())
            assert data["mine_type"] in valid_types, (
                f"{f.name}: invalid mine_type '{data['mine_type']}'"
            )
