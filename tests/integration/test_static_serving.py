"""Integration tests for static file serving and the GET / route."""

import time

import pytest


class TestIndexRoute:
    """GET / serves the frontend HTML."""

    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_content_type_is_html(self, client):
        resp = client.get("/")
        assert "text/html" in resp.headers["content-type"]

    def test_index_contains_app_title(self, client):
        resp = client.get("/")
        assert b"unearthed" in resp.content

    def test_index_contains_entry_point_script(self, client):
        resp = client.get("/")
        assert b"/static/js/app.js" in resp.content

    def test_index_contains_stylesheet_link(self, client):
        resp = client.get("/")
        assert b"/static/style.css" in resp.content

    def test_index_contains_maplibre_cdn(self, client):
        resp = client.get("/")
        assert b"maplibre-gl" in resp.content

    def test_index_contains_pixijs_cdn(self, client):
        resp = client.get("/")
        assert b"pixi" in resp.content


class TestStaticFiles:
    """Static CSS and JS files are served correctly."""

    def test_style_css_served(self, client):
        resp = client.get("/static/style.css")
        assert resp.status_code == 200
        assert "text/css" in resp.headers["content-type"]

    def test_app_js_served(self, client):
        resp = client.get("/static/js/app.js")
        assert resp.status_code == 200

    def test_api_js_served(self, client):
        resp = client.get("/static/js/api.js")
        assert resp.status_code == 200

    def test_geo_js_served(self, client):
        resp = client.get("/static/js/geo.js")
        assert resp.status_code == 200

    def test_map_js_served(self, client):
        resp = client.get("/static/js/map.js")
        assert resp.status_code == 200

    def test_particles_js_served(self, client):
        resp = client.get("/static/js/particles.js")
        assert resp.status_code == 200

    def test_chat_js_served(self, client):
        resp = client.get("/static/js/chat.js")
        assert resp.status_code == 200

    def test_nonexistent_static_returns_404(self, client):
        resp = client.get("/static/doesnotexist.js")
        assert resp.status_code == 404


class TestGeoJsonServing:
    """GeoJSON data file is served from static/data/."""

    def test_geojson_served(self, client):
        resp = client.get("/static/data/egrid_subregions.geojson")
        assert resp.status_code == 200

    def test_geojson_is_valid_json(self, client):
        resp = client.get("/static/data/egrid_subregions.geojson")
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) > 0

    def test_geojson_features_have_subregion_property(self, client):
        resp = client.get("/static/data/egrid_subregions.geojson")
        data = resp.json()
        for feature in data["features"]:
            assert "Subregion" in feature["properties"]

    def test_internal_assets_not_exposed(self, client):
        resp = client.get("/assets/semantic_model.yaml")
        assert resp.status_code == 404


class TestHtmlStructure:
    """Validate that index.html contains all required DOM elements."""

    @pytest.fixture(autouse=True)
    def _load_html(self, client):
        self.html = client.get("/").text

    def test_has_intro_section(self):
        assert 'id="intro"' in self.html

    def test_has_map_section(self):
        assert 'id="map-section"' in self.html

    def test_has_reveal_section(self):
        assert 'id="reveal-section"' in self.html

    def test_has_locate_button(self):
        assert 'id="btn-locate"' in self.html

    def test_has_state_picker(self):
        assert 'id="state-picker"' in self.html

    def test_has_map_container(self):
        assert 'id="map-container"' in self.html

    def test_has_particle_canvas(self):
        assert 'id="particle-canvas"' in self.html

    def test_has_ticker(self):
        assert 'id="ticker-value"' in self.html

    def test_has_prose_element(self):
        assert 'id="prose"' in self.html

    def test_has_chat_form(self):
        assert 'id="chat-form"' in self.html

    def test_has_chat_input(self):
        assert 'id="chat-input"' in self.html

    def test_has_chat_chips(self):
        assert 'id="chat-chips"' in self.html

    def test_has_chat_transcript(self):
        assert 'id="chat-transcript"' in self.html

    def test_has_share_button(self):
        assert 'id="btn-share"' in self.html

    def test_has_mine_detail_elements(self):
        assert 'id="detail-mine"' in self.html
        assert 'id="detail-operator"' in self.html
        assert 'id="detail-county"' in self.html
        assert 'id="detail-type"' in self.html
        assert 'id="detail-plant"' in self.html
        assert 'id="detail-tons"' in self.html

    def test_has_og_meta_tags(self):
        assert 'property="og:title"' in self.html
        assert 'property="og:description"' in self.html

    def test_has_viewport_meta(self):
        assert 'name="viewport"' in self.html

    def test_has_footer_with_data_sources(self):
        assert "MSHA" in self.html
        assert "EIA" in self.html

    def test_has_hero_image_container(self):
        assert 'id="hero-image"' in self.html

    def test_has_error_message_element(self):
        assert 'id="error-message"' in self.html

    def test_has_loading_spinner(self):
        assert 'id="loading-spinner"' in self.html

    def test_chat_input_has_maxlength(self):
        assert 'maxlength="500"' in self.html


class TestApiEndpointsStillWork:
    """Verify that static file mounting hasn't broken API endpoints."""

    def test_mine_for_me_post_still_validates(self, client):
        resp = client.post("/mine-for-me", json={})
        assert resp.status_code == 422

    def test_ask_post_still_validates(self, client):
        resp = client.post("/ask", json={})
        assert resp.status_code == 422

    def test_mine_for_me_get_returns_405(self, client):
        resp = client.get("/mine-for-me")
        assert resp.status_code == 405

    def test_ask_get_returns_405(self, client):
        resp = client.get("/ask")
        assert resp.status_code == 405


class TestStaticServingPerformance:
    """Static files should be served quickly."""

    @pytest.mark.timeout(2)
    def test_index_under_100ms(self, client):
        start = time.perf_counter()
        resp = client.get("/")
        elapsed = time.perf_counter() - start
        assert resp.status_code == 200
        assert elapsed < 0.5, f"Index took {elapsed:.3f}s"

    @pytest.mark.timeout(2)
    def test_css_under_100ms(self, client):
        start = time.perf_counter()
        resp = client.get("/static/style.css")
        elapsed = time.perf_counter() - start
        assert resp.status_code == 200
        assert elapsed < 0.5, f"CSS took {elapsed:.3f}s"

    @pytest.mark.timeout(2)
    def test_js_under_100ms(self, client):
        start = time.perf_counter()
        resp = client.get("/static/js/app.js")
        elapsed = time.perf_counter() - start
        assert resp.status_code == 200
        assert elapsed < 0.5, f"JS took {elapsed:.3f}s"
