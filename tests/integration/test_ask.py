"""Integration tests for POST /ask endpoint."""

from unittest.mock import patch


class TestAskEndpoint:
    @patch("app.main.execute_analyst_sql", return_value=[{"TOTAL": 42}])
    @patch(
        "app.main.query_cortex_analyst",
        return_value={
            "answer": "",
            "interpretation": "This is our interpretation of your question: How much coal?",
            "sql": "SELECT ...",
            "error": None,
        },
    )
    def test_success_returns_interpretation_and_results(self, mock_cortex, mock_exec, client):
        resp = client.post("/ask", json={"question": "How much coal?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == ""
        expected = "This is our interpretation of your question: How much coal?"
        assert data["interpretation"] == expected
        assert data["sql"] == "SELECT ..."
        assert data["results"] == [{"TOTAL": 42}]
        assert data["error"] is None
        assert data["suggestions"] is not None

    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "Result", "interpretation": None, "sql": None, "error": None},
    )
    def test_optional_subregion_passed(self, mock_cortex, client):
        resp = client.post("/ask", json={"question": "How much?", "subregion_id": "SRVC"})
        assert resp.status_code == 200

    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "", "interpretation": None, "sql": None, "error": "Out of scope"},
    )
    def test_error_returned_in_response(self, mock_cortex, client):
        resp = client.post("/ask", json={"question": "What's the weather?"})
        data = resp.json()
        assert data["error"] == "Out of scope"
        assert data["answer"] == ""

    @patch(
        "app.main.query_cortex_analyst",
        return_value={
            "answer": "I cannot answer questions about weather.",
            "interpretation": None,
            "sql": None,
            "error": None,
        },
    )
    def test_text_answer_no_sql_returned_directly(self, mock_cortex, client):
        """Out-of-scope: text answer with no SQL flows through untouched."""
        resp = client.post("/ask", json={"question": "What's the weather?"})
        data = resp.json()
        assert data["answer"] == "I cannot answer questions about weather."
        assert data["interpretation"] is None
        assert data["sql"] is None
        assert data["results"] is None


class TestAskSuggestions:
    @patch(
        "app.main.query_cortex_analyst",
        return_value={
            "answer": "Try one of these:",
            "interpretation": None,
            "sql": None,
            "error": None,
            "suggestions": ["How many mines in PA?", "Total tonnage by state?"],
        },
    )
    def test_suggestions_returned(self, mock_cortex, client):
        resp = client.post("/ask", json={"question": "Help me"})
        data = resp.json()
        assert data["suggestions"] == [
            "How many mines in PA?",
            "Total tonnage by state?",
        ]

    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "42", "interpretation": None, "sql": None, "error": None},
    )
    def test_no_analyst_suggestions_returns_defaults(self, mock_cortex, client):
        resp = client.post("/ask", json={"question": "How much coal?"})
        data = resp.json()
        assert len(data["suggestions"]) == 5


class TestAskSqlExecution:
    @patch("app.main.execute_analyst_sql", return_value=[{"TOTAL": 5000000}])
    @patch(
        "app.main.query_cortex_analyst",
        return_value={
            "answer": "",
            "interpretation": "This is our interpretation: total tonnage?",
            "sql": "SELECT SUM(TOTAL_TONS) AS TOTAL FROM ...",
            "error": None,
        },
    )
    def test_sql_results_included(self, mock_cortex, mock_exec, client):
        resp = client.post("/ask", json={"question": "Total tonnage?"})
        data = resp.json()
        assert data["results"] == [{"TOTAL": 5000000}]
        assert data["sql"] == "SELECT SUM(TOTAL_TONS) AS TOTAL FROM ..."
        assert data["interpretation"] == "This is our interpretation: total tonnage?"
        mock_exec.assert_called_once_with("SELECT SUM(TOTAL_TONS) AS TOTAL FROM ...")

    @patch("app.main.execute_analyst_sql", side_effect=Exception("DB error"))
    @patch(
        "app.main.query_cortex_analyst",
        return_value={
            "answer": "",
            "interpretation": "This is our interpretation: total?",
            "sql": "SELECT ...",
            "error": None,
        },
    )
    def test_sql_execution_failure_replaces_answer(self, mock_cortex, mock_exec, client):
        resp = client.post("/ask", json={"question": "Total?"})
        data = resp.json()
        assert data["answer"] == "I could not answer that confidently."
        assert data["error"] is not None
        assert data["sql"] == "SELECT ..."
        assert data["results"] is None
        assert data["interpretation"] is None

    @patch(
        "app.main.query_cortex_analyst",
        return_value={"answer": "No data", "interpretation": None, "sql": None, "error": None},
    )
    def test_no_sql_skips_execution(self, mock_cortex, client):
        resp = client.post("/ask", json={"question": "Help?"})
        data = resp.json()
        assert data["results"] is None


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
