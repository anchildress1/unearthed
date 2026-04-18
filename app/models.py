from pydantic import BaseModel, Field


class MineForMeRequest(BaseModel):
    subregion_id: str = Field(min_length=1, max_length=10)


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


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    subregion_id: str | None = Field(default=None, min_length=1, max_length=10)


class AskResponse(BaseModel):
    answer: str
    sql: str | None = None
    error: str | None = None
    suggestions: list[str] | None = None
    results: list[dict] | None = None
