from httpx import AsyncClient
from src.utils.db_manager import DBManager


async def test_add_booking_valid_dates(ac: AsyncClient, db: DBManager):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    response = await ac.post(
        "/bookings",
        json={
            "room_id": 1,
            "date_from": "2026-11-10",
            "date_to": "2026-11-15",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    booking_id = data["id"]

    try:
        assert data["room_id"] == 1
        assert data["date_from"] == "2026-11-10"
        assert data["date_to"] == "2026-11-15"
    finally:
        await db.bookings.delete(id=booking_id)
        await db.commit()


async def test_add_booking_same_dates_returns_422(ac: AsyncClient):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    response = await ac.post(
        "/bookings",
        json={
            "room_id": 1,
            "date_from": "2026-11-10",
            "date_to": "2026-11-10",
        },
    )

    assert response.status_code == 422


async def test_add_booking_date_to_before_date_from_returns_422(ac: AsyncClient):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    response = await ac.post(
        "/bookings",
        json={
            "room_id": 1,
            "date_from": "2026-11-15",
            "date_to": "2026-11-10",
        },
    )

    assert response.status_code == 422
