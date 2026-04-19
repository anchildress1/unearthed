from pydantic import BaseModel, Field, StrictStr, field_validator

_SUBREGION_PATTERN = r"^[A-Za-z0-9]{2,10}$"


class MineForMeRequest(BaseModel):
    subregion_id: StrictStr = Field(pattern=_SUBREGION_PATTERN)


class MineForMeResponse(BaseModel):
    mine: str
    mine_operator: str
    mine_county: str
    mine_state: str
    mine_type: str
    mine_coords: list[float] = Field(min_length=2, max_length=2)
    plant: str
    plant_operator: str
    plant_coords: list[float] = Field(min_length=2, max_length=2)
    tons: float = Field(ge=0)
    tons_year: int
    prose: str
    subregion_id: str
    user_coords: list[float] | None = None
    degraded: bool = False

    model_config = {"extra": "forbid"}

    @field_validator("mine_coords", "plant_coords")
    @classmethod
    def validate_coords(cls, v: list[float]) -> list[float]:
        lat, lon = v
        if not (-90 <= lat <= 90):
            raise ValueError(f"Latitude {lat} out of range [-90, 90]")
        if not (-180 <= lon <= 180):
            raise ValueError(f"Longitude {lon} out of range [-180, 180]")
        return v


class AskRequest(BaseModel):
    question: StrictStr = Field(min_length=1, max_length=500)
    subregion_id: StrictStr | None = Field(
        default=None,
        pattern=_SUBREGION_PATTERN,
    )


class AskResponse(BaseModel):
    answer: str = Field(
        description=(
            "Text answer from Cortex Analyst, or empty string when SQL results are the answer."
        ),
    )
    interpretation: str | None = Field(
        default=None,
        description=(
            "Analyst's internal restatement of the question, shown as a dim label when SQL "
            "results are present. None when SQL execution failed or no SQL was generated."
        ),
    )
    sql: str | None = Field(
        default=None,
        description="Generated SQL statement, if any.",
    )
    error: str | None = Field(
        default=None,
        description="Error message when the query could not be answered or executed.",
    )
    suggestions: list[str] | None = Field(
        default=None,
        description="Follow-up question suggestions.",
    )
    results: list[dict] | None = Field(
        default=None,
        description="Rows returned by executing the generated SQL (capped at 500).",
    )

    model_config = {"extra": "forbid"}
