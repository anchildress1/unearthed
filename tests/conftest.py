import pytest
from fastapi.testclient import TestClient

# Internal mine data (includes stats for prose generation).
SAMPLE_MINE_DATA = {
    "mine": "Bailey Mine",
    "mine_id": "36609947",
    "mine_operator": "Consol Pennsylvania Coal Company LLC",
    "mine_county": "Greene",
    "mine_state": "PA",
    "mine_type": "Underground",
    "mine_coords": [39.9175, -80.471944],
    "plant": "Cross",
    "plant_operator": "South Carolina Public Service Authority",
    "plant_coords": [33.371506, -80.113235],
    "tons": 1247001.0,
    "tons_year": 2024,
    "fatalities": 3,
    "injuries": 12,
    "days_lost": 640,
}

SAMPLE_MINE_DATA_SURFACE = {
    **SAMPLE_MINE_DATA,
    "mine": "Hobet Mine",
    "mine_type": "Surface",
    "mine_county": "Boone",
    "mine_state": "WV",
}

# Keys that are internal-only (not part of MineForMeResponse).
_INTERNAL_KEYS = {"fatalities", "injuries", "days_lost"}


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def sample_mine_data():
    """Mine data for MineForMeResponse tests — excludes internal-only keys."""
    return {k: v for k, v in SAMPLE_MINE_DATA.items() if k not in _INTERNAL_KEYS}


@pytest.fixture
def sample_mine_data_surface():
    return {k: v for k, v in SAMPLE_MINE_DATA_SURFACE.items() if k not in _INTERNAL_KEYS}
