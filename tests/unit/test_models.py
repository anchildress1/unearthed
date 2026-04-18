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

    def test_min_length_subregion_accepted(self):
        req = MineForMeRequest(subregion_id="AB")
        assert req.subregion_id == "AB"

    def test_max_length_subregion_accepted(self):
        req = MineForMeRequest(subregion_id="ABCDEFGHIJ")  # 10 chars
        assert req.subregion_id == "ABCDEFGHIJ"

    def test_one_over_max_length_rejected(self):
        with pytest.raises(ValidationError):
            MineForMeRequest(subregion_id="ABCDEFGHIJK")  # 11 chars

    def test_one_char_subregion_rejected(self):
        with pytest.raises(ValidationError):
            MineForMeRequest(subregion_id="X")

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

    def test_space_in_subregion_rejected(self):
        with pytest.raises(ValidationError):
            MineForMeRequest(subregion_id="SR VC")

    def test_semicolon_injection_rejected(self):
        with pytest.raises(ValidationError):
            MineForMeRequest(subregion_id="SRVC;")

    def test_alphanumeric_mixed_accepted(self):
        req = MineForMeRequest(subregion_id="SR1C")
        assert req.subregion_id == "SR1C"


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

    def test_mine_coords_out_of_range_lat_rejected(self, sample_mine_data):
        sample_mine_data["mine_coords"] = [91.0, -80.0]
        with pytest.raises(ValidationError):
            MineForMeResponse(**sample_mine_data, prose="Bad.", subregion_id="SRVC")

    def test_mine_coords_out_of_range_negative_lat_rejected(self, sample_mine_data):
        sample_mine_data["mine_coords"] = [-91.0, -80.0]
        with pytest.raises(ValidationError):
            MineForMeResponse(**sample_mine_data, prose="Bad.", subregion_id="SRVC")

    def test_mine_coords_out_of_range_lon_rejected(self, sample_mine_data):
        sample_mine_data["mine_coords"] = [39.0, 181.0]
        with pytest.raises(ValidationError):
            MineForMeResponse(**sample_mine_data, prose="Bad.", subregion_id="SRVC")

    def test_mine_coords_boundary_lat_90_accepted(self, sample_mine_data):
        sample_mine_data["mine_coords"] = [90.0, -80.0]
        resp = MineForMeResponse(**sample_mine_data, prose="Boundary.", subregion_id="SRVC")
        assert resp.mine_coords[0] == 90.0

    def test_mine_coords_boundary_lat_minus_90_accepted(self, sample_mine_data):
        sample_mine_data["mine_coords"] = [-90.0, -80.0]
        resp = MineForMeResponse(**sample_mine_data, prose="Boundary.", subregion_id="SRVC")
        assert resp.mine_coords[0] == -90.0

    def test_mine_coords_boundary_lon_180_accepted(self, sample_mine_data):
        sample_mine_data["mine_coords"] = [39.0, 180.0]
        resp = MineForMeResponse(**sample_mine_data, prose="Boundary.", subregion_id="SRVC")
        assert resp.mine_coords[1] == 180.0

    def test_plant_coords_out_of_range_rejected(self, sample_mine_data):
        sample_mine_data["plant_coords"] = [33.0, -181.0]
        with pytest.raises(ValidationError):
            MineForMeResponse(**sample_mine_data, prose="Bad.", subregion_id="SRVC")

    def test_user_coords_none_by_default(self, sample_mine_data):
        resp = MineForMeResponse(**sample_mine_data, prose="Test.", subregion_id="SRVC")
        assert resp.user_coords is None

    def test_user_coords_accepted(self, sample_mine_data):
        resp = MineForMeResponse(
            **sample_mine_data,
            prose="Test.",
            subregion_id="SRVC",
            user_coords=[34.0, -81.0],
        )
        assert resp.user_coords == [34.0, -81.0]

    def test_extra_field_rejected(self, sample_mine_data):
        with pytest.raises(ValidationError):
            MineForMeResponse(
                **sample_mine_data,
                prose="Test.",
                subregion_id="SRVC",
                unknown_field="bad",
            )

    def test_mine_coords_one_element_rejected(self, sample_mine_data):
        sample_mine_data["mine_coords"] = [39.0]
        with pytest.raises(ValidationError):
            MineForMeResponse(**sample_mine_data, prose="Bad.", subregion_id="SRVC")

    def test_mine_coords_three_elements_rejected(self, sample_mine_data):
        sample_mine_data["mine_coords"] = [39.0, -80.0, 100.0]
        with pytest.raises(ValidationError):
            MineForMeResponse(**sample_mine_data, prose="Bad.", subregion_id="SRVC")


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

    def test_max_length_question_accepted(self):
        req = AskRequest(question="x" * 500)
        assert len(req.question) == 500

    def test_over_max_length_question_rejected(self):
        with pytest.raises(ValidationError):
            AskRequest(question="x" * 501)

    def test_subregion_id_min_length_accepted(self):
        req = AskRequest(question="How much?", subregion_id="AB")
        assert req.subregion_id == "AB"

    def test_subregion_id_max_length_accepted(self):
        req = AskRequest(question="How much?", subregion_id="ABCDEFGHIJ")
        assert req.subregion_id == "ABCDEFGHIJ"

    def test_subregion_id_over_max_length_rejected(self):
        with pytest.raises(ValidationError):
            AskRequest(question="How much?", subregion_id="ABCDEFGHIJK")

    def test_subregion_id_one_char_rejected(self):
        with pytest.raises(ValidationError):
            AskRequest(question="How much?", subregion_id="X")

    def test_subregion_id_special_chars_rejected(self):
        with pytest.raises(ValidationError):
            AskRequest(question="How much?", subregion_id="../bad")

    def test_question_is_strict_str(self):
        with pytest.raises(ValidationError):
            AskRequest(question=42)

    def test_unicode_question_accepted(self):
        req = AskRequest(question="日本語の質問")
        assert req.question == "日本語の質問"


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

    def test_interpretation_field_none_by_default(self):
        resp = AskResponse(answer="42")
        assert resp.interpretation is None

    def test_interpretation_field_set(self):
        resp = AskResponse(answer="", interpretation="This is our interpretation.")
        assert resp.interpretation == "This is our interpretation."

    def test_all_optional_fields_none(self):
        resp = AskResponse(answer="")
        assert resp.sql is None
        assert resp.error is None
        assert resp.suggestions is None
        assert resp.results is None
        assert resp.interpretation is None

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            AskResponse(answer="42", unknown_field="bad")

    def test_results_empty_list_accepted(self):
        resp = AskResponse(answer="No data", results=[])
        assert resp.results == []

    def test_multiple_results_rows(self):
        rows = [{"A": 1}, {"A": 2}, {"A": 3}]
        resp = AskResponse(answer="", results=rows)
        assert len(resp.results) == 3
