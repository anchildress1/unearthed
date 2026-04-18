"""Unit tests validating JavaScript module content and structure.

These tests read the JS source files and verify they contain
expected exports, function signatures, and data structures
without executing the JS.
"""

from pathlib import Path

import pytest

JS_DIR = Path(__file__).parent.parent.parent / "static" / "js"


class TestApiJsContent:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = (JS_DIR / "api.js").read_text()

    def test_exports_fetch_mine_for_me(self):
        assert "export async function fetchMineForMe" in self.src

    def test_exports_fetch_ask(self):
        assert "export async function fetchAsk" in self.src

    def test_posts_to_mine_for_me_endpoint(self):
        assert "/mine-for-me" in self.src

    def test_posts_to_ask_endpoint(self):
        assert "/ask" in self.src

    def test_sets_content_type_json(self):
        assert '"Content-Type": "application/json"' in self.src

    def test_uses_post_method(self):
        assert 'method: "POST"' in self.src

    def test_sends_subregion_id_in_body(self):
        assert "subregion_id" in self.src

    def test_handles_non_ok_responses(self):
        assert "resp.ok" in self.src

    def test_no_hardcoded_localhost(self):
        assert "localhost" not in self.src
        assert "127.0.0.1" not in self.src


class TestGeoJsContent:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = (JS_DIR / "geo.js").read_text()

    def test_exports_state_to_subregion(self):
        assert "export const STATE_TO_SUBREGION" in self.src

    def test_exports_request_location(self):
        assert "export function requestLocation" in self.src

    def test_exports_load_subregion_geojson(self):
        assert "export async function loadSubregionGeoJSON" in self.src

    def test_exports_find_subregion(self):
        assert "export function findSubregion" in self.src

    def test_exports_has_coal_data(self):
        assert "export function hasCoalData" in self.src

    def test_exports_subregion_for_state(self):
        assert "export function subregionForState" in self.src

    def test_contains_all_50_states_plus_dc(self):
        states = [
            "AL",
            "AK",
            "AZ",
            "AR",
            "CA",
            "CO",
            "CT",
            "DE",
            "FL",
            "GA",
            "HI",
            "ID",
            "IL",
            "IN",
            "IA",
            "KS",
            "KY",
            "LA",
            "ME",
            "MD",
            "MA",
            "MI",
            "MN",
            "MS",
            "MO",
            "MT",
            "NE",
            "NV",
            "NH",
            "NJ",
            "NM",
            "NY",
            "NC",
            "ND",
            "OH",
            "OK",
            "OR",
            "PA",
            "RI",
            "SC",
            "SD",
            "TN",
            "TX",
            "UT",
            "VT",
            "VA",
            "WA",
            "WV",
            "WI",
            "WY",
            "DC",
        ]
        for state in states:
            assert f'  {state}: "' in self.src, f"Missing state {state}"

    def test_ray_casting_algorithm_present(self):
        assert "pointInRing" in self.src

    def test_handles_multipolygon(self):
        assert "MultiPolygon" in self.src

    def test_handles_polygon(self):
        assert '"Polygon"' in self.src

    def test_fetches_geojson_from_static_data(self):
        assert "/static/data/egrid_subregions.geojson" in self.src

    def test_coal_subregions_set(self):
        assert "COAL_SUBREGIONS" in self.src
        assert "SRVC" in self.src
        assert "ERCT" in self.src


class TestMapJsContent:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = (JS_DIR / "map.js").read_text()

    def test_exports_create_map(self):
        assert "export function createMap" in self.src

    def test_exports_run_reveal_sequence(self):
        assert "export function runRevealSequence" in self.src

    def test_uses_maplibregl(self):
        assert "maplibregl.Map" in self.src

    def test_uses_maplibre_marker(self):
        assert "maplibregl.Marker" in self.src

    def test_uses_fly_to(self):
        assert "flyTo" in self.src

    def test_uses_fit_bounds(self):
        assert "fitBounds" in self.src

    def test_has_arc_line_function(self):
        assert "addArcLine" in self.src

    def test_draws_geojson_line(self):
        assert "LineString" in self.src

    def test_uses_dark_style(self):
        assert "dark" in self.src.lower()

    def test_has_load_timeout(self):
        assert "MAP_LOAD_TIMEOUT_MS" in self.src

    def test_rejects_on_timeout(self):
        assert "reject" in self.src


class TestParticlesJsContent:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = (JS_DIR / "particles.js").read_text()

    def test_exports_create_particle_overlay(self):
        assert "export function createParticleOverlay" in self.src

    def test_exports_show_hero_image(self):
        assert "export function showHeroImage" in self.src

    def test_exports_start_ticker(self):
        assert "export function startTicker" in self.src

    def test_exports_tons_per_second(self):
        assert "export function tonsPerSecond" in self.src

    def test_uses_particle_container(self):
        assert "ParticleContainer" in self.src

    def test_has_max_particles_limit(self):
        assert "MAX_PARTICLES" in self.src

    def test_seconds_in_year_constant(self):
        assert "SECONDS_IN_YEAR" in self.src

    def test_uses_request_animation_frame(self):
        assert "requestAnimationFrame" in self.src

    def test_has_cancel_animation_frame(self):
        assert "cancelAnimationFrame" in self.src

    def test_hero_images_for_both_types(self):
        assert "Surface" in self.src
        assert "Underground" in self.src

    def test_ticker_shows_two_decimal_places(self):
        assert "toFixed(2)" in self.src

    def test_no_innerhtml_usage(self):
        assert "innerHTML" not in self.src


class TestChatJsContent:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = (JS_DIR / "chat.js").read_text()

    def test_exports_init_chat(self):
        assert "export function initChat" in self.src

    def test_imports_fetch_ask(self):
        assert "fetchAsk" in self.src

    def test_has_default_chips(self):
        assert "DEFAULT_CHIPS" in self.src

    def test_chip_questions_cover_prd_patterns(self):
        assert "produced since" in self.src
        assert "plants buy from" in self.src
        assert "still active" in self.src
        assert "total coal tonnage" in self.src
        assert "largest coal supplier" in self.src

    def test_renders_sql_toggle(self):
        assert "Show SQL" in self.src
        assert "Hide SQL" in self.src

    def test_renders_error_class(self):
        assert "chat__error" in self.src

    def test_renders_loading_indicator(self):
        assert "Thinking..." in self.src

    def test_renders_results_table(self):
        assert "renderResultsTable" in self.src

    def test_no_innerhtml_usage(self):
        assert "innerHTML" not in self.src

    def test_handles_suggestions(self):
        assert "suggestions" in self.src

    def test_uses_text_content_not_innerhtml(self):
        assert "textContent" in self.src

    def test_uses_abort_controller_for_listener_cleanup(self):
        assert "AbortController" in self.src

    def test_has_concurrent_request_protection(self):
        assert "chatBusy" in self.src

    def test_disables_form_during_request(self):
        assert "setFormEnabled" in self.src


class TestAppJsContent:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = (JS_DIR / "app.js").read_text()

    def test_imports_all_modules(self):
        assert "from ./api.js" in self.src.replace('"', "").replace("'", "")
        assert "from ./chat.js" in self.src.replace('"', "").replace("'", "")
        assert "from ./geo.js" in self.src.replace('"', "").replace("'", "")
        assert "from ./map.js" in self.src.replace('"', "").replace("'", "")
        assert "from ./particles.js" in self.src.replace('"', "").replace("'", "")

    def test_handles_share_url(self):
        assert "URLSearchParams" in self.src

    def test_share_url_uses_s_param(self):
        assert '"s"' in self.src or "'s'" in self.src

    def test_validates_share_url_param(self):
        assert "[A-Za-z0-9]" in self.src

    def test_populates_state_picker(self):
        assert "populateStatePicker" in self.src

    def test_has_section_transition_logic(self):
        assert "showSection" in self.src

    def test_handles_outside_us(self):
        assert "outside" in self.src.lower() or "geo-outside-us" in self.src

    def test_has_error_handling(self):
        assert "showError" in self.src
        assert "hideError" in self.src

    def test_shows_loading_spinner(self):
        assert "showLoading" in self.src

    def test_has_all_state_labels(self):
        assert "West Virginia" in self.src
        assert "Wyoming" in self.src
        assert "California" in self.src

    def test_fills_mine_details(self):
        assert "detailMine" in self.src
        assert "detailOperator" in self.src
        assert "detailCounty" in self.src
        assert "detailPlant" in self.src
        assert "detailTons" in self.src

    def test_starts_particle_overlay(self):
        assert "createParticleOverlay" in self.src
        assert "startTicker" in self.src

    def test_initializes_chat(self):
        assert "initChat" in self.src

    def test_clipboard_copy_for_share(self):
        assert "navigator.clipboard" in self.src

    def test_no_innerhtml_usage(self):
        assert "innerHTML" not in self.src

    def test_has_cleanup_function(self):
        assert "cleanup" in self.src

    def test_stores_ticker_stop(self):
        assert "tickerStop" in self.src

    def test_stores_pixi_app(self):
        assert "pixiApp" in self.src

    def test_removes_share_handler_on_re_reveal(self):
        assert "removeEventListener" in self.src

    def test_checks_cdn_dependencies(self):
        assert "maplibregl" in self.src
        assert "PIXI" in self.src

    def test_pixi_failure_caught(self):
        assert "Particle overlay unavailable" in self.src

    def test_clipboard_failure_handled(self):
        assert "Could not copy link" in self.src

    def test_map_instance_disposed_on_cleanup(self):
        assert "mapInstance" in self.src
        assert ".remove()" in self.src

    def test_concurrent_reveal_guard(self):
        assert "revealInProgress" in self.src
