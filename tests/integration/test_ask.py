"""Integration tests for POST /ask endpoint."""

from unittest.mock import patch


class TestAskEndpoint:
    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "42 million tons", "sql": "SELECT ...", "error": None},
    )
    def test_success_returns_answer(self, mock_cortex, client):
        resp = client.post("/ask", json={"question": "How much coal?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "42 million tons"
        assert data["sql"] == "SELECT ..."
        assert data["error"] is None

    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "Result", "sql": None, "error": None},
    )
    def test_optional_subregion_passed(self, mock_cortex, client):
        resp = client.post(
            "/ask", json={"question": "How much?", "subregion_id": "SRVC"}
        )
        assert resp.status_code == 200

    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "", "sql": None, "error": "Out of scope"},
    )
    def test_error_returned_in_response(self, mock_cortex, client):
        resp = client.post("/ask", json={"question": "What's the weather?"})
        data = resp.json()
        assert data["error"] == "Out of scope"
        assert data["answer"] == ""


class TestAskCortexFailure:
    @patch("app.main.query_cortex_analyst", side_effect=Exception("Service unavailable"))
    def test_cortex_down_returns_error(self, mock_cortex, client):
        resp = client.post("/ask", json={"question": "How much coal?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is not None
        assert "unavailable" in data["error"].lower()
        assert data["answer"] == ""


class TestAskValidation:
    def test_missing_body_returns_422(self, client):
        resp = client.post("/ask")
        assert resp.status_code == 422

    def test_empty_json_returns_422(self, client):
        resp = client.post("/ask", json={})
        assert resp.status_code == 422

    def test_get_method_not_allowed(self, client):
        resp = client.get("/ask")
        assert resp.status_code == 405

    def test_empty_question_returns_422(self, client):
        resp = client.post("/ask", json={"question": ""})
        assert resp.status_code == 422
