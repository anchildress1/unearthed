"""Unit tests for Pydantic request/response models."""

import pytest
from pydantic import ValidationError

from app.models import AskRequest, AskResponse, MineForMeRequest, MineForMeResponse

# --- MineForMeRequest ---


class TestMineForMeRequest:
    def test_valid_subregion(self):
        req = MineForMeRequest(subregion_id="SRVC")
        assert req.subregion_id == "SRVC"

    def test_lowercase_subregion_preserved(self):
        req = MineForMeRequest(subregion_id="srvc")
        assert req.subregion_id == "srvc"

    def test_empty_subregion_rejected(self):
        with pytest.raises(ValidationError):
            MineForMeRequest(subregion_id="")

    def test_missing_subregion_rejects(self):
        with pytest.raises(ValidationError):
            MineForMeRequest()

    def test_null_subregion_rejects(self):
        with pytest.raises(ValidationError):
            MineForMeRequest(subregion_id=None)

    def test_numeric_subregion_rejects(self):
        with pytest.raises(ValidationError):
            MineForMeRequest(subregion_id=123)

    def test_path_traversal_rejected(self):
        with pytest.raises(ValidationError):
            MineForMeRequest(subregion_id="../../etc")

    def test_special_chars_rejected(self):
        with pytest.raises(ValidationError):
            MineForMeRequest(subregion_id="../bad")


# --- MineForMeResponse ---


class TestMineForMeResponse:
    def test_valid_response(self, sample_mine_data):
        resp = MineForMeResponse(
            **sample_mine_data,
            prose="Test prose.",
            subregion_id="SRVC",
        )
        assert resp.mine == "Bailey Mine"
        assert resp.degraded is False

    def test_degraded_flag_default_false(self, sample_mine_data):
        resp = MineForMeResponse(
            **sample_mine_data,
            prose="Test.",
            subregion_id="SRVC",
        )
        assert resp.degraded is False

    def test_degraded_flag_explicit_true(self, sample_mine_data):
        resp = MineForMeResponse(
            **sample_mine_data,
            prose="Fallback.",
            subregion_id="SRVC",
            degraded=True,
        )
        assert resp.degraded is True

    def test_coords_as_two_element_list(self, sample_mine_data):
        resp = MineForMeResponse(
            **sample_mine_data,
            prose="Test.",
            subregion_id="SRVC",
        )
        assert len(resp.mine_coords) == 2
        assert len(resp.plant_coords) == 2

    def test_missing_required_field_rejects(self):
        with pytest.raises(ValidationError):
            MineForMeResponse(mine="Test", prose="Test.", subregion_id="X")

    def test_tons_zero_accepted(self, sample_mine_data):
        sample_mine_data["tons"] = 0
        resp = MineForMeResponse(
            **sample_mine_data,
            prose="No tonnage.",
            subregion_id="SRVC",
        )
        assert resp.tons == 0.0

    def test_negative_tons_rejected(self, sample_mine_data):
        sample_mine_data["tons"] = -1.0
        with pytest.raises(ValidationError):
            MineForMeResponse(
                **sample_mine_data,
                prose="Negative.",
                subregion_id="SRVC",
            )


# --- AskRequest ---


class TestAskRequest:
    def test_question_only(self):
        req = AskRequest(question="How much coal?")
        assert req.question == "How much coal?"
        assert req.subregion_id is None

    def test_question_with_subregion(self):
        req = AskRequest(question="How much?", subregion_id="RFCW")
        assert req.subregion_id == "RFCW"

    def test_missing_question_rejects(self):
        with pytest.raises(ValidationError):
            AskRequest()

    def test_empty_question_rejected(self):
        with pytest.raises(ValidationError):
            AskRequest(question="")


# --- AskResponse ---


class TestAskResponse:
    def test_answer_only(self):
        resp = AskResponse(answer="42 million tons")
        assert resp.answer == "42 million tons"
        assert resp.sql is None
        assert resp.error is None

    def test_answer_with_sql(self):
        resp = AskResponse(answer="42", sql="SELECT SUM(tons) FROM ...")
        assert resp.sql == "SELECT SUM(tons) FROM ..."

    def test_error_response(self):
        resp = AskResponse(answer="", error="Query failed")
        assert resp.error == "Query failed"
        assert resp.answer == ""

    def test_suggestions_field(self):
        resp = AskResponse(answer="", suggestions=["Try asking X", "Try asking Y"])
        assert resp.suggestions == ["Try asking X", "Try asking Y"]

    def test_results_field(self):
        resp = AskResponse(answer="42", results=[{"TOTAL_TONS": 42}])
        assert resp.results == [{"TOTAL_TONS": 42}]
