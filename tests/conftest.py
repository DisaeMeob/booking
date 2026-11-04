import json
import pytest
from httpx import AsyncClient, ASGITransport

from config import settings
from database import async_session_maker_null_pool
from schemas.hotels import HotelAdd
from schemas.rooms import RoomsAdd
from src.database import Base, engine_null_pool
from src.main import app
from src.models import *
from utils.db_manager import DBManager

@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    assert settings.MODE == "TEST"


@pytest.fixture(scope="function")
async def db():
    async with DBManager(session_factory=async_session_maker_null_pool) as db:
        yield db


@pytest.fixture(scope="session", autouse=True)
async def ac():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="session", autouse=True)
async def async_main(setup_database):
    async with engine_null_pool.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    with open("tests/mock_hotels.json", encoding="utf-8") as file_hotels:
        hotels_json = json.load(file_hotels)

    with open("tests/mock_rooms.json", encoding="utf-8") as file_rooms:
        rooms_json = json.load(file_rooms)

    hotels = [HotelAdd.model_validate(hotel) for hotel in hotels_json]
    rooms = [RoomsAdd.model_validate(room) for room in rooms_json]

    async with DBManager(session_factory=async_session_maker_null_pool) as db_:
        await db_.hotels.add_bulk(hotels)
        await db_.rooms.add_bulk(rooms)
        await db_.commit()


@pytest.fixture(scope="session", autouse=True)
async def register_user(ac):
    await ac.post(
        "/auth/register",
        json={
            "email": "kot@pes.com",
            "password": "12345678",
        }
    )