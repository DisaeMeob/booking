import asyncio
from httpx import AsyncClient
from src.schemas.rooms import RoomsAdd
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


async def test_booking_room_not_found(ac: AsyncClient):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    response = await ac.post(
        "/bookings",
        json={
            "room_id": 999999,
            "date_from": "2027-01-10",
            "date_to": "2027-01-15",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Room not found"


async def test_booking_quantity_one_and_exhaustion(ac: AsyncClient, db: DBManager):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    # Создаём комнату с quantity=1
    temp_room = await db.rooms.add(
        RoomsAdd(
            hotel_id=1,
            title="Single room test",
            description="desc",
            price=5000,
            quantity=1,
        )
    )
    await db.commit()

    created_booking_id = None
    try:
        # Первое бронирование — успешно
        res1 = await ac.post(
            "/bookings",
            json={
                "room_id": temp_room.id,
                "date_from": "2027-02-01",
                "date_to": "2027-02-10",
            },
        )
        assert res1.status_code == 200
        created_booking_id = res1.json()["data"]["id"]

        # Второе бронирование на пересекающиеся даты — 409
        res2 = await ac.post(
            "/bookings",
            json={
                "room_id": temp_room.id,
                "date_from": "2027-02-05",
                "date_to": "2027-02-15",
            },
        )
        assert res2.status_code == 409
    finally:
        if created_booking_id is not None:
            await db.bookings.delete(id=created_booking_id)
        await db.rooms.delete(id=temp_room.id)
        await db.commit()


async def test_booking_quantity_two_and_exhaustion(ac: AsyncClient, db: DBManager):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    # Создаём комнату с quantity=2
    temp_room = await db.rooms.add(
        RoomsAdd(
            hotel_id=1,
            title="Double room test",
            description="desc",
            price=6000,
            quantity=2,
        )
    )
    await db.commit()

    b1_id, b2_id = None, None
    try:
        # Первое бронирование — успешно
        res1 = await ac.post(
            "/bookings",
            json={
                "room_id": temp_room.id,
                "date_from": "2027-03-01",
                "date_to": "2027-03-10",
            },
        )
        assert res1.status_code == 200
        b1_id = res1.json()["data"]["id"]

        # Второе бронирование на пересекающиеся даты — успешно (quantity=2)
        res2 = await ac.post(
            "/bookings",
            json={
                "room_id": temp_room.id,
                "date_from": "2027-03-05",
                "date_to": "2027-03-15",
            },
        )
        assert res2.status_code == 200
        b2_id = res2.json()["data"]["id"]

        # Третье бронирование при исчерпании мест — 409
        res3 = await ac.post(
            "/bookings",
            json={
                "room_id": temp_room.id,
                "date_from": "2027-03-07",
                "date_to": "2027-03-09",
            },
        )
        assert res3.status_code == 409
    finally:
        if b1_id is not None:
            await db.bookings.delete(id=b1_id)
        if b2_id is not None:
            await db.bookings.delete(id=b2_id)
        await db.rooms.delete(id=temp_room.id)
        await db.commit()


async def test_booking_boundary_dates_touching_allowed(ac: AsyncClient, db: DBManager):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    # Создаём комнату с quantity=1
    temp_room = await db.rooms.add(
        RoomsAdd(
            hotel_id=1,
            title="Boundary dates test",
            description="desc",
            price=7000,
            quantity=1,
        )
    )
    await db.commit()

    b1_id, b2_id = None, None
    try:
        # Бронь 1: 2027-04-01 -> 2027-04-05
        res1 = await ac.post(
            "/bookings",
            json={
                "room_id": temp_room.id,
                "date_from": "2027-04-01",
                "date_to": "2027-04-05",
            },
        )
        assert res1.status_code == 200
        b1_id = res1.json()["data"]["id"]

        # Бронь 2 в день выезда предыдущей: 2027-04-05 -> 2027-04-10 — успешно (не пересекаются)
        res2 = await ac.post(
            "/bookings",
            json={
                "room_id": temp_room.id,
                "date_from": "2027-04-05",
                "date_to": "2027-04-10",
            },
        )
        assert res2.status_code == 200
        b2_id = res2.json()["data"]["id"]
    finally:
        if b1_id is not None:
            await db.bookings.delete(id=b1_id)
        if b2_id is not None:
            await db.bookings.delete(id=b2_id)
        await db.rooms.delete(id=temp_room.id)
        await db.commit()


async def test_concurrent_booking_last_room(ac: AsyncClient, db: DBManager):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    # Создаём комнату с quantity=1
    temp_room = await db.rooms.add(
        RoomsAdd(
            hotel_id=1,
            title="Concurrent room test",
            description="desc",
            price=8000,
            quantity=1,
        )
    )
    await db.commit()

    created_booking_ids: list[int] = []
    try:
        # Два одновременных запроса на один и тот же последний свободный номер
        booking_payload = {
            "room_id": temp_room.id,
            "date_from": "2027-05-01",
            "date_to": "2027-05-10",
        }
        res1, res2 = await asyncio.gather(
            ac.post("/bookings", json=booking_payload),
            ac.post("/bookings", json=booking_payload),
        )

        # Сначала собираем id всех успешно созданных броней (для надёжной очистки даже при 2x 200)
        created_booking_ids = [
            r.json()["data"]["id"]
            for r in (res1, res2)
            if r.status_code == 200 and "data" in r.json() and "id" in r.json()["data"]
        ]

        # Теперь проверяем статусы
        status_codes = sorted([res1.status_code, res2.status_code])
        # Ровно один запрос успешен (200), а второй отклонён из-за отсутствия мест (409)
        assert status_codes == [200, 409]
        assert len(created_booking_ids) == 1
    finally:
        for b_id in created_booking_ids:
            await db.bookings.delete(id=b_id)
        await db.rooms.delete(id=temp_room.id)
        await db.commit()


async def test_get_all_bookings_returns_405_method_not_allowed(ac: AsyncClient):
    response = await ac.get("/bookings")
    assert response.status_code == 405


async def test_get_my_bookings_unauthorized_returns_401(ac: AsyncClient):
    # Очищаем cookies перед запросом
    ac.cookies.clear()
    response = await ac.get("/bookings/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Вы не предоставили токен доступа"


async def test_get_my_bookings_returns_only_current_user_bookings(ac: AsyncClient, db: DBManager):
    from src.schemas.bookings import BookingsAdd
    from src.services.auth import AuthService
    from src.schemas.users import UserAdd

    other_user_id: int | None = None
    other_booking_id: int | None = None
    my_booking_id: int | None = None

    try:
        # 1. Создаём второго пользователя напрямую через БД
        other_user = await db.users.add(
            UserAdd(
                email="other_user@pes.com",
                hashed_password=AuthService().hash_password("secret123"),
            )
        )
        other_user_id = other_user.id

        # Создаём чужое бронирование для other_user
        other_booking = await db.bookings.add(
            BookingsAdd(
                user_id=other_user.id,
                room_id=1,
                price=24500,
                date_from="2027-12-01",
                date_to="2027-12-05",
            )
        )
        other_booking_id = other_booking.id
        await db.commit()

        # 2. Логинимся под основным пользователем kot@pes.com
        ac.cookies.clear()
        login_response = await ac.post(
            "/auth/login",
            json={"email": "kot@pes.com", "password": "12345678"},
        )
        assert login_response.status_code == 200

        # 3. Создаём бронирование от лица kot@pes.com через API
        my_booking_res = await ac.post(
            "/bookings",
            json={
                "room_id": 1,
                "date_from": "2027-11-20",
                "date_to": "2027-11-25",
            },
        )
        assert my_booking_res.status_code == 200
        my_booking_id = my_booking_res.json()["data"]["id"]

        # 4. Запрашиваем свои бронирования
        res = await ac.get("/bookings/me")
        assert res.status_code == 200
        my_bookings_data = res.json()["data"]

        # Проверяем, что в списке есть наше бронирование
        my_booking_ids = [b["id"] for b in my_bookings_data]
        assert my_booking_id in my_booking_ids

        # Проверяем, что чужого бронирования НЕТ в списке
        assert other_booking_id not in my_booking_ids

        # Все возвращённые брони принадлежат kot@pes.com
        user_me_res = await ac.get("/auth/me")
        assert user_me_res.status_code == 200
        current_user_id = user_me_res.json()["id"]
        assert all(b["user_id"] == current_user_id for b in my_bookings_data)
    finally:
        # Удаляем только успешно созданные записи: сначала бронирования, затем пользователя
        if my_booking_id is not None:
            await db.bookings.delete(id=my_booking_id)
        if other_booking_id is not None:
            await db.bookings.delete(id=other_booking_id)
        if other_user_id is not None:
            await db.users.delete(id=other_user_id)
        await db.commit()
