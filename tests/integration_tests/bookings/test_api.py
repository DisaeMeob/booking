import asyncio
from datetime import date, timedelta
from httpx import AsyncClient
from src.schemas.rooms import RoomsAdd
from src.utils.db_manager import DBManager


async def test_add_booking_valid_dates(ac: AsyncClient, db: DBManager):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    today = date.today()
    date_from = (today + timedelta(days=3)).isoformat()
    date_to = (today + timedelta(days=8)).isoformat()
    expected_days = (date.fromisoformat(date_to) - date.fromisoformat(date_from)).days

    response = await ac.post(
        "/bookings",
        json={
            "room_id": 1,
            "date_from": date_from,
            "date_to": date_to,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    booking_id = data["id"]

    try:
        assert data["room_id"] == 1
        assert data["date_from"] == date_from
        assert data["date_to"] == date_to
        assert "total_cost" in data
        assert data["total_cost"] == data["price"] * expected_days
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

        # Все возвращённые брони принадлежат kot@pes.com и содержат корректный total_cost
        user_me_res = await ac.get("/auth/me")
        assert user_me_res.status_code == 200
        current_user_id = user_me_res.json()["id"]
        assert all(b["user_id"] == current_user_id for b in my_bookings_data)

        from datetime import date
        for b in my_bookings_data:
            assert "total_cost" in b
            b_days = (date.fromisoformat(b["date_to"]) - date.fromisoformat(b["date_from"])).days
            assert b["total_cost"] == b["price"] * b_days
    finally:
        # Удаляем только успешно созданные записи: сначала бронирования, затем пользователя
        if my_booking_id is not None:
            await db.bookings.delete(id=my_booking_id)
        if other_booking_id is not None:
            await db.bookings.delete(id=other_booking_id)
        if other_user_id is not None:
            await db.users.delete(id=other_user_id)
        await db.commit()


async def test_add_booking_date_from_in_past_returns_422(ac: AsyncClient):
    from datetime import date, timedelta

    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    past_date_from = (date.today() - timedelta(days=1)).isoformat()
    future_date_to = (date.today() + timedelta(days=2)).isoformat()

    response = await ac.post(
        "/bookings",
        json={
            "room_id": 1,
            "date_from": past_date_from,
            "date_to": future_date_to,
        },
    )
    assert response.status_code == 422


async def test_add_booking_both_dates_in_past_returns_422(ac: AsyncClient):
    from datetime import date, timedelta

    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    past_date_from = (date.today() - timedelta(days=5)).isoformat()
    past_date_to = (date.today() - timedelta(days=1)).isoformat()

    response = await ac.post(
        "/bookings",
        json={
            "room_id": 1,
            "date_from": past_date_from,
            "date_to": past_date_to,
        },
    )
    assert response.status_code == 422


async def test_add_booking_date_from_today_success(ac: AsyncClient, db: DBManager):
    from datetime import date, timedelta

    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    today = date.today()
    today_date_from = today.isoformat()
    future_date_to = (today + timedelta(days=2)).isoformat()

    booking_id: int | None = None
    try:
        response = await ac.post(
            "/bookings",
            json={
                "room_id": 1,
                "date_from": today_date_from,
                "date_to": future_date_to,
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        booking_id = data["id"]
        assert data["room_id"] == 1
        assert data["date_from"] == today_date_from
        assert data["date_to"] == future_date_to
    finally:
        if booking_id is not None:
            await db.bookings.delete(id=booking_id)
            await db.commit()


async def test_booking_total_cost_calculation(ac: AsyncClient, db: DBManager):
    from datetime import date, timedelta

    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    today = date.today()

    # 1. Проверяем проживание на 1 ночь
    d_from_1 = (today + timedelta(days=20)).isoformat()
    d_to_1 = (today + timedelta(days=21)).isoformat()
    expected_days_1 = (date.fromisoformat(d_to_1) - date.fromisoformat(d_from_1)).days
    assert expected_days_1 == 1

    # 2. Проверяем проживание на несколько ночей (например, 4 ночи)
    d_from_4 = (today + timedelta(days=25)).isoformat()
    d_to_4 = (today + timedelta(days=29)).isoformat()
    expected_days_4 = (date.fromisoformat(d_to_4) - date.fromisoformat(d_from_4)).days
    assert expected_days_4 == 4

    b1_id: int | None = None
    b2_id: int | None = None

    try:
        # Запрос на 1 ночь
        res1 = await ac.post(
            "/bookings",
            json={
                "room_id": 1,
                "date_from": d_from_1,
                "date_to": d_to_1,
            },
        )
        assert res1.status_code == 200
        data1 = res1.json()["data"]
        b1_id = data1["id"]
        assert "total_cost" in data1
        assert data1["total_cost"] == data1["price"] * expected_days_1

        # Запрос на несколько ночей
        res2 = await ac.post(
            "/bookings",
            json={
                "room_id": 1,
                "date_from": d_from_4,
                "date_to": d_to_4,
            },
        )
        assert res2.status_code == 200
        data2 = res2.json()["data"]
        b2_id = data2["id"]
        assert "total_cost" in data2
        assert data2["total_cost"] == data2["price"] * expected_days_4
    finally:
        if b1_id is not None:
            await db.bookings.delete(id=b1_id)
        if b2_id is not None:
            await db.bookings.delete(id=b2_id)
        await db.commit()


async def test_delete_user_booking_success(ac: AsyncClient, db: DBManager):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    today = date.today()
    date_from = (today + timedelta(days=35)).isoformat()
    date_to = (today + timedelta(days=40)).isoformat()

    booking_id: int | None = None
    try:
        # Создаём бронирование
        create_res = await ac.post(
            "/bookings",
            json={
                "room_id": 1,
                "date_from": date_from,
                "date_to": date_to,
            },
        )
        assert create_res.status_code == 200
        booking_id = create_res.json()["data"]["id"]

        # Успешно удаляем собственное бронирование
        del_res = await ac.delete(f"/bookings/{booking_id}")
        assert del_res.status_code == 200
        assert del_res.json() == {"status": "Ok"}

        # Проверяем, что в списке бронирований его больше нет
        my_bookings_res = await ac.get("/bookings/me")
        assert my_bookings_res.status_code == 200
        my_booking_ids = [b["id"] for b in my_bookings_res.json()["data"]]
        assert booking_id not in my_booking_ids
        booking_id = None
    finally:
        if booking_id is not None:
            await db.bookings.delete(id=booking_id)
            await db.commit()


async def test_delete_other_user_booking_returns_404(ac: AsyncClient, db: DBManager):
    from src.schemas.bookings import BookingsAdd
    from src.services.auth import AuthService
    from src.schemas.users import UserAdd

    other_user_id: int | None = None
    other_booking_id: int | None = None

    try:
        # Создаём чужого пользователя и его бронирование
        other_user = await db.users.add(
            UserAdd(
                email="victim_user@pes.com",
                hashed_password=AuthService().hash_password("secret123"),
            )
        )
        other_user_id = other_user.id

        today = date.today()
        other_booking = await db.bookings.add(
            BookingsAdd(
                user_id=other_user.id,
                room_id=1,
                price=24500,
                date_from=today + timedelta(days=45),
                date_to=today + timedelta(days=50),
            )
        )
        other_booking_id = other_booking.id
        await db.commit()

        # Логинимся под обычным пользователем kot@pes.com
        ac.cookies.clear()
        login_res = await ac.post(
            "/auth/login",
            json={"email": "kot@pes.com", "password": "12345678"},
        )
        assert login_res.status_code == 200

        # Пытаемся удалить чужое бронирование
        del_res = await ac.delete(f"/bookings/{other_booking_id}")
        assert del_res.status_code == 404
        assert del_res.json()["detail"] == "Бронирование не найдено"

        # Проверяем, что чужая запись осталась в базе данных
        existing_booking = await db.bookings.get_one_or_none(id=other_booking_id)
        assert existing_booking is not None
        assert existing_booking.id == other_booking_id
    finally:
        if other_booking_id is not None:
            await db.bookings.delete(id=other_booking_id)
        if other_user_id is not None:
            await db.users.delete(id=other_user_id)
        await db.commit()


async def test_delete_booking_not_found(ac: AsyncClient):
    login_res = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_res.status_code == 200

    del_res = await ac.delete("/bookings/999999")
    assert del_res.status_code == 404
    assert del_res.json()["detail"] == "Бронирование не найдено"


async def test_delete_booking_twice_returns_404(ac: AsyncClient, db: DBManager):
    login_res = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_res.status_code == 200

    today = date.today()
    date_from = (today + timedelta(days=55)).isoformat()
    date_to = (today + timedelta(days=60)).isoformat()

    booking_id: int | None = None
    try:
        create_res = await ac.post(
            "/bookings",
            json={
                "room_id": 1,
                "date_from": date_from,
                "date_to": date_to,
            },
        )
        assert create_res.status_code == 200
        booking_id = create_res.json()["data"]["id"]

        # Первое удаление — 200 OK
        del_res1 = await ac.delete(f"/bookings/{booking_id}")
        assert del_res1.status_code == 200
        assert del_res1.json() == {"status": "Ok"}

        # Повторное удаление той же брони — 404 Not Found
        del_res2 = await ac.delete(f"/bookings/{booking_id}")
        assert del_res2.status_code == 404
        assert del_res2.json()["detail"] == "Бронирование не найдено"
        booking_id = None
    finally:
        if booking_id is not None:
            await db.bookings.delete(id=booking_id)
            await db.commit()


async def test_delete_booking_frees_up_room_for_new_booking(ac: AsyncClient, db: DBManager):
    login_res = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_res.status_code == 200

    temp_room = await db.rooms.add(
        RoomsAdd(
            hotel_id=1,
            title="Room for delete & rebook test",
            description="desc",
            price=7500,
            quantity=1,
        )
    )
    await db.commit()

    today = date.today()
    payload = {
        "room_id": temp_room.id,
        "date_from": (today + timedelta(days=65)).isoformat(),
        "date_to": (today + timedelta(days=70)).isoformat(),
    }

    first_booking_id: int | None = None
    second_booking_id: int | None = None

    try:
        res1 = await ac.post("/bookings", json=payload)
        assert res1.status_code == 200
        first_booking_id = res1.json()["data"]["id"]

        res_conflict = await ac.post("/bookings", json=payload)
        assert res_conflict.status_code == 409

        del_res = await ac.delete(f"/bookings/{first_booking_id}")
        assert del_res.status_code == 200
        assert del_res.json() == {"status": "Ok"}
        first_booking_id = None

        res2 = await ac.post("/bookings", json=payload)
        assert res2.status_code == 200
        second_booking_id = res2.json()["data"]["id"]
    finally:
        if first_booking_id is not None:
            await db.bookings.delete(id=first_booking_id)
        if second_booking_id is not None:
            await db.bookings.delete(id=second_booking_id)
        await db.rooms.delete(id=temp_room.id)
        await db.commit()
