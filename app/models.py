from pydantic import BaseModel


class MineForMeRequest(BaseModel):
    subregion_id: str


class MineForMeResponse(BaseModel):
    mine: str
    mine_operator: str
    mine_county: str
    mine_state: str
    mine_type: str
    mine_coords: list[float]
    plant: str
    plant_operator: str
    plant_coords: list[float]
    tons: float
    tons_year: int
    prose: str
    subregion_id: str
    degraded: bool = False


class AskRequest(BaseModel):
    question: str
    subregion_id: str | None = None


class AskResponse(BaseModel):
    answer: str
    sql: str | None = None
    error: str | None = None
