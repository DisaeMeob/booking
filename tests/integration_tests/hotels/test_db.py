from database import async_session_maker
from schemas.hotels import HotelAdd
from utils.db_manager import DBManager


async def test_add_hotel(db: DBManager):
    hotel_data = HotelAdd(title="Hotel 1", location="Сочи")
    await db.hotels.add(hotel_data)
    await db.commit()