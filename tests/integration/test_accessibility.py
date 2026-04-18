"""Accessibility and SEO checks — Lighthouse CI equivalent.

Tests the same checks Lighthouse performs for accessibility, SEO,
and best practices, without requiring a running browser.
"""

import re

import pytest


@pytest.fixture()
def html(client):
    return client.get("/").text


class TestAccessibility:
    """WCAG and Lighthouse accessibility checks."""

    def test_html_has_lang_attribute(self, html):
        assert 'lang="en"' in html

    def test_has_document_title(self, html):
        assert "<title>" in html
        assert "</title>" in html

    def test_viewport_meta_present(self, html):
        assert 'name="viewport"' in html

    def test_viewport_has_width(self, html):
        match = re.search(r'<meta[^>]*name="viewport"[^>]*content="([^"]*)"', html)
        assert match
        assert "width=" in match.group(1)

    def test_charset_is_utf8(self, html):
        assert 'charset="UTF-8"' in html or 'charset="utf-8"' in html

    def test_buttons_have_text_content(self, html):
        # Buttons should not be empty — find <button> tags with content
        buttons = re.findall(r"<button[^>]*>(.*?)</button>", html, re.DOTALL)
        for btn in buttons:
            stripped = btn.strip()
            assert stripped, f"Found empty button: {btn!r}"

    def test_inputs_have_labels_or_aria(self, html):
        # All input elements should have an associated label or aria-label
        inputs = re.findall(r'<input[^>]*id="([^"]*)"[^>]*/?\s*>', html)
        for input_id in inputs:
            has_label = f'for="{input_id}"' in html
            has_aria = "aria-label" in html
            assert has_label or has_aria, f"Input #{input_id} has no <label for> or aria-label"

    def test_form_has_accessible_submit(self, html):
        assert 'type="submit"' in html

    def test_no_autoplaying_media(self, html):
        assert "autoplay" not in html.lower()

    def test_heading_hierarchy_starts_with_h1(self, html):
        h1_pos = html.find("<h1")
        h2_pos = html.find("<h2")
        if h2_pos != -1:
            assert h1_pos != -1, "h2 without h1"
            assert h1_pos < h2_pos, "h2 appears before h1"

    def test_select_has_default_option(self, html):
        # State picker should have a default/placeholder option
        assert '<option value=""' in html


class TestSeoMeta:
    """SEO checks matching Lighthouse SEO audit."""

    def test_has_og_title(self, html):
        assert 'property="og:title"' in html

    def test_has_og_description(self, html):
        assert 'property="og:description"' in html

    def test_has_og_type(self, html):
        assert 'property="og:type"' in html

    def test_has_twitter_card(self, html):
        assert 'name="twitter:card"' in html

    def test_title_not_empty(self, html):
        match = re.search(r"<title>(.*?)</title>", html)
        assert match
        assert len(match.group(1).strip()) > 0

    def test_og_description_is_reasonable_length(self, html):
        match = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]*)"', html)
        assert match
        desc = match.group(1)
        assert 30 <= len(desc) <= 160, f"OG description length {len(desc)} not ideal"


class TestBestPractices:
    """Lighthouse best practices checks."""

    def test_doctype_present(self, html):
        assert html.strip().startswith("<!DOCTYPE html>")

    def test_no_unsafe_dom_manipulation(self, html):
        # No direct DOM string injection in inline scripts
        assert "document.write" not in html  # noqa: S105 — this is a test assertion

    def test_scripts_use_type_module_or_defer(self, html):
        # App script should use type="module"
        assert 'type="module"' in html

    def test_stylesheet_link_present(self, html):
        assert 'rel="stylesheet"' in html

    def test_no_inline_styles_on_body(self, html):
        body_match = re.search(r"<body[^>]*>", html)
        assert body_match
        assert "style=" not in body_match.group(0)

    def test_no_javascript_urls(self, html):
        assert "javascript:" not in html.lower()

    def test_external_scripts_are_https(self, html):
        script_srcs = re.findall(r'<script[^>]*src="([^"]*)"', html)
        for src in script_srcs:
            if src.startswith("http"):
                assert src.startswith("https://"), f"Non-HTTPS script: {src}"

    def test_external_stylesheets_are_https(self, html):
        link_hrefs = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]*)"', html)
        for href in link_hrefs:
            if href.startswith("http"):
                assert href.startswith("https://"), f"Non-HTTPS stylesheet: {href}"
