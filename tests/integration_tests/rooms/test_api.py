from httpx import AsyncClient
from src.schemas.facilities import FacilityAdd
from src.utils.db_manager import DBManager


async def test_get_rooms_by_hotel(ac: AsyncClient):
    response = await ac.get(
        "/hotels/1/rooms",
        params={
            "date_from": "2026-10-03",
            "date_to": "2026-10-10",
        },
    )

    assert response.status_code == 200
    rooms = response.json()
    assert isinstance(rooms, list)
    assert len(rooms) >= 1
    assert all(room["hotel_id"] == 1 for room in rooms)


async def test_get_room_success(ac: AsyncClient):
    response = await ac.get("/hotels/1/rooms/1")

    assert response.status_code == 200
    room = response.json()
    assert room["id"] == 1
    assert room["hotel_id"] == 1


async def test_get_room_not_found(ac: AsyncClient):
    response = await ac.get("/hotels/1/rooms/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Room not found"


async def test_get_room_wrong_hotel_id(ac: AsyncClient):
    response = await ac.get("/hotels/2/rooms/1")

    assert response.status_code == 404
    assert response.json()["detail"] == "Room not found"


async def test_create_room_hotel_not_found(ac: AsyncClient):
    response = await ac.post(
        "/hotels/9999/rooms",
        json={
            "title": "Люкс",
            "description": "Описание",
            "price": 15000,
            "quantity": 2,
            "facilities_ids": [],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Hotel not found"


async def test_edit_and_patch_room_wrong_hotel_preserves_data(
    ac: AsyncClient,
    db: DBManager,
):
    initial_room = await db.rooms.get_one_or_none(hotel_id=1, id=1)
    assert initial_room is not None
    original_facilities_ids = [f.id for f in initial_room.facilities]

    facility = await db.facilities.add(
        FacilityAdd(title="Unique Test Facility For Room 1 Protection")
    )
    await db.commit()

    test_facilities_ids = [*original_facilities_ids, facility.id]

    try:
        await db.room_facility.set_room_facilities(
            room_id=1,
            facilities_ids=test_facilities_ids,
        )
        await db.commit()

        room_before = await db.rooms.get_one_or_none(hotel_id=1, id=1)
        assert room_before is not None
        assert set(f.id for f in room_before.facilities) == set(test_facilities_ids)

        put_response = await ac.put(
            "/hotels/2/rooms/1",
            json={
                "title": "Чужой PUT",
                "description": "Попытка перезаписи",
                "price": 1,
                "quantity": 1,
                "facilities_ids": [],
            },
        )
        assert put_response.status_code == 404
        assert put_response.json()["detail"] == "Room not found"

        patch_response = await ac.patch(
            "/hotels/2/rooms/1",
            json={
                "title": "Чужой PATCH",
                "facilities_ids": [],
            },
        )
        assert patch_response.status_code == 404
        assert patch_response.json()["detail"] == "Room not found"

        room_after = await db.rooms.get_one_or_none(hotel_id=1, id=1)
        assert room_after is not None
        assert room_after.id == room_before.id
        assert room_after.hotel_id == room_before.hotel_id
        assert room_after.title == room_before.title
        assert room_after.description == room_before.description
        assert room_after.price == room_before.price
        assert room_after.quantity == room_before.quantity
        assert set(f.id for f in room_after.facilities) == set(test_facilities_ids)
    finally:
        await db.room_facility.set_room_facilities(
            room_id=1,
            facilities_ids=original_facilities_ids,
        )
        await db.facilities.delete(id=facility.id)
        await db.commit()


async def test_delete_room_not_found(ac: AsyncClient):
    response = await ac.delete("/hotels/1/rooms/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Room not found"


async def test_delete_room_wrong_hotel_id(ac: AsyncClient):
    response = await ac.delete("/hotels/2/rooms/1")

    assert response.status_code == 404
    assert response.json()["detail"] == "Room not found"

    get_response = await ac.get("/hotels/1/rooms/1")
    assert get_response.status_code == 200


async def test_delete_room_success(ac: AsyncClient):
    create_response = await ac.post(
        "/hotels/1/rooms",
        json={
            "title": "Временный номер для удаления",
            "description": "Будет удалён в тесте",
            "price": 5000,
            "quantity": 1,
            "facilities_ids": [],
        },
    )
    assert create_response.status_code == 200
    created_room_id = create_response.json()["data"]["id"]

    delete_response = await ac.delete(f"/hotels/1/rooms/{created_room_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "ok"}

    get_response = await ac.get(f"/hotels/1/rooms/{created_room_id}")
    assert get_response.status_code == 404


async def test_edit_room_put_cannot_decrease_below_peak_occupancy(ac: AsyncClient, db: DBManager):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    create_res = await ac.post(
        "/hotels/1/rooms",
        json={
            "title": "Room for PUT test",
            "description": "desc",
            "price": 10000,
            "quantity": 3,
            "facilities_ids": [],
        },
    )
    assert create_res.status_code == 200
    room_id = create_res.json()["data"]["id"]

    b1_res = await ac.post(
        "/bookings",
        json={"room_id": room_id, "date_from": "2027-08-01", "date_to": "2027-08-10"},
    )
    assert b1_res.status_code == 200
    b1_id = b1_res.json()["data"]["id"]

    b2_res = await ac.post(
        "/bookings",
        json={"room_id": room_id, "date_from": "2027-08-05", "date_to": "2027-08-15"},
    )
    assert b2_res.status_code == 200
    b2_id = b2_res.json()["data"]["id"]

    try:
        # Пытаемся сделать PUT с quantity=1 при пиковой занятости 2 -> 409
        put_res = await ac.put(
            f"/hotels/1/rooms/{room_id}",
            json={
                "title": "Room for PUT test updated",
                "description": "desc updated",
                "price": 10000,
                "quantity": 1,
                "facilities_ids": [],
            },
        )
        assert put_res.status_code == 409

        # Проверяем, что в базе quantity осталось 3
        get_res = await ac.get(f"/hotels/1/rooms/{room_id}")
        assert get_res.status_code == 200
        assert get_res.json()["quantity"] == 3
    finally:
        await db.bookings.delete(id=b1_id)
        await db.bookings.delete(id=b2_id)
        await db.rooms.delete(id=room_id)
        await db.commit()


async def test_patch_room_cannot_decrease_below_peak_occupancy(ac: AsyncClient, db: DBManager):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    create_res = await ac.post(
        "/hotels/1/rooms",
        json={
            "title": "Room for PATCH test",
            "description": "desc",
            "price": 10000,
            "quantity": 3,
            "facilities_ids": [],
        },
    )
    assert create_res.status_code == 200
    room_id = create_res.json()["data"]["id"]

    b1_res = await ac.post(
        "/bookings",
        json={"room_id": room_id, "date_from": "2027-08-01", "date_to": "2027-08-10"},
    )
    assert b1_res.status_code == 200
    b1_id = b1_res.json()["data"]["id"]

    b2_res = await ac.post(
        "/bookings",
        json={"room_id": room_id, "date_from": "2027-08-05", "date_to": "2027-08-15"},
    )
    assert b2_res.status_code == 200
    b2_id = b2_res.json()["data"]["id"]

    try:
        # Пытаемся сделать PATCH с quantity=1 при пиковой занятости 2 -> 409
        patch_res = await ac.patch(
            f"/hotels/1/rooms/{room_id}",
            json={"quantity": 1},
        )
        assert patch_res.status_code == 409

        # Проверяем, что в базе quantity осталось 3
        get_res = await ac.get(f"/hotels/1/rooms/{room_id}")
        assert get_res.status_code == 200
        assert get_res.json()["quantity"] == 3
    finally:
        await db.bookings.delete(id=b1_id)
        await db.bookings.delete(id=b2_id)
        await db.rooms.delete(id=room_id)
        await db.commit()


async def test_patch_room_decrease_to_peak_occupancy_allowed(ac: AsyncClient, db: DBManager):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    create_res = await ac.post(
        "/hotels/1/rooms",
        json={
            "title": "Room for exact peak test",
            "description": "desc",
            "price": 10000,
            "quantity": 3,
            "facilities_ids": [],
        },
    )
    assert create_res.status_code == 200
    room_id = create_res.json()["data"]["id"]

    b1_res = await ac.post(
        "/bookings",
        json={"room_id": room_id, "date_from": "2027-08-01", "date_to": "2027-08-10"},
    )
    assert b1_res.status_code == 200
    b1_id = b1_res.json()["data"]["id"]

    b2_res = await ac.post(
        "/bookings",
        json={"room_id": room_id, "date_from": "2027-08-05", "date_to": "2027-08-15"},
    )
    assert b2_res.status_code == 200
    b2_id = b2_res.json()["data"]["id"]

    try:
        # Уменьшение ровно до пиковой занятости (2) разрешено
        patch_res = await ac.patch(
            f"/hotels/1/rooms/{room_id}",
            json={"quantity": 2},
        )
        assert patch_res.status_code == 200

        get_res = await ac.get(f"/hotels/1/rooms/{room_id}")
        assert get_res.status_code == 200
        assert get_res.json()["quantity"] == 2
    finally:
        await db.bookings.delete(id=b1_id)
        await db.bookings.delete(id=b2_id)
        await db.rooms.delete(id=room_id)
        await db.commit()


async def test_patch_room_increase_quantity_allowed(ac: AsyncClient, db: DBManager):
    create_res = await ac.post(
        "/hotels/1/rooms",
        json={
            "title": "Room for increase test",
            "description": "desc",
            "price": 10000,
            "quantity": 3,
            "facilities_ids": [],
        },
    )
    assert create_res.status_code == 200
    room_id = create_res.json()["data"]["id"]

    try:
        # Увеличение quantity всегда разрешено
        patch_res = await ac.patch(
            f"/hotels/1/rooms/{room_id}",
            json={"quantity": 5},
        )
        assert patch_res.status_code == 200

        get_res = await ac.get(f"/hotels/1/rooms/{room_id}")
        assert get_res.status_code == 200
        assert get_res.json()["quantity"] == 5
    finally:
        await db.rooms.delete(id=room_id)
        await db.commit()


async def test_patch_room_without_quantity_succeeds(ac: AsyncClient, db: DBManager):
    create_res = await ac.post(
        "/hotels/1/rooms",
        json={
            "title": "Room title before",
            "description": "desc before",
            "price": 10000,
            "quantity": 3,
            "facilities_ids": [],
        },
    )
    assert create_res.status_code == 200
    room_id = create_res.json()["data"]["id"]

    try:
        # PATCH без quantity обновляет только указанные поля
        patch_res = await ac.patch(
            f"/hotels/1/rooms/{room_id}",
            json={"title": "Room title after"},
        )
        assert patch_res.status_code == 200

        get_res = await ac.get(f"/hotels/1/rooms/{room_id}")
        assert get_res.status_code == 200
        assert get_res.json()["title"] == "Room title after"
        assert get_res.json()["quantity"] == 3
    finally:
        await db.rooms.delete(id=room_id)
        await db.commit()


async def test_patch_room_quantity_null_returns_422(ac: AsyncClient, db: DBManager):
    create_res = await ac.post(
        "/hotels/1/rooms",
        json={
            "title": "Room null quantity test",
            "description": "desc",
            "price": 10000,
            "quantity": 3,
            "facilities_ids": [],
        },
    )
    assert create_res.status_code == 200
    room_id = create_res.json()["data"]["id"]

    try:
        # Явный null в quantity возвращает 422
        patch_res = await ac.patch(
            f"/hotels/1/rooms/{room_id}",
            json={"quantity": None},
        )
        assert patch_res.status_code == 422
    finally:
        await db.rooms.delete(id=room_id)
        await db.commit()


async def test_peak_occupancy_event_algorithm_non_overlapping_bookings(ac: AsyncClient, db: DBManager):
    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    create_res = await ac.post(
        "/hotels/1/rooms",
        json={
            "title": "Room for algorithm test",
            "description": "desc",
            "price": 10000,
            "quantity": 4,
            "facilities_ids": [],
        },
    )
    assert create_res.status_code == 200
    room_id = create_res.json()["data"]["id"]

    # Три бронирования:
    # A: 2027-07-01 -> 2027-07-10
    # B: 2027-07-01 -> 2027-07-03
    # C: 2027-07-07 -> 2027-07-10
    # B и C не пересекаются друг с другом, поэтому пиковая занятость = 2 (а не 3!)
    res_a = await ac.post(
        "/bookings",
        json={"room_id": room_id, "date_from": "2027-07-01", "date_to": "2027-07-10"},
    )
    assert res_a.status_code == 200
    b_a_id = res_a.json()["data"]["id"]

    res_b = await ac.post(
        "/bookings",
        json={"room_id": room_id, "date_from": "2027-07-01", "date_to": "2027-07-03"},
    )
    assert res_b.status_code == 200
    b_b_id = res_b.json()["data"]["id"]

    res_c = await ac.post(
        "/bookings",
        json={"room_id": room_id, "date_from": "2027-07-07", "date_to": "2027-07-10"},
    )
    assert res_c.status_code == 200
    b_c_id = res_c.json()["data"]["id"]

    try:
        # Уменьшение до 2 допустимо, так как реальный пик занятости 2
        patch_allowed = await ac.patch(
            f"/hotels/1/rooms/{room_id}",
            json={"quantity": 2},
        )
        assert patch_allowed.status_code == 200

        # Уменьшение до 1 запрещено (пик 2 > 1) -> 409
        patch_forbidden = await ac.patch(
            f"/hotels/1/rooms/{room_id}",
            json={"quantity": 1},
        )
        assert patch_forbidden.status_code == 409
    finally:
        await db.bookings.delete(id=b_a_id)
        await db.bookings.delete(id=b_b_id)
        await db.bookings.delete(id=b_c_id)
        await db.rooms.delete(id=room_id)
        await db.commit()


async def test_concurrent_booking_and_patch_quantity_preserves_invariant(ac: AsyncClient, db: DBManager):
    import asyncio

    login_response = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_response.status_code == 200

    create_res = await ac.post(
        "/hotels/1/rooms",
        json={
            "title": "Concurrent room quantity test",
            "description": "desc",
            "price": 10000,
            "quantity": 2,
            "facilities_ids": [],
        },
    )
    assert create_res.status_code == 200
    room_id = create_res.json()["data"]["id"]

    # Создаём 1 бронь
    initial_b = await ac.post(
        "/bookings",
        json={"room_id": room_id, "date_from": "2027-09-01", "date_to": "2027-09-10"},
    )
    assert initial_b.status_code == 200
    initial_b_id = initial_b.json()["data"]["id"]

    created_booking_ids = [initial_b_id]
    try:
        # Одновременно:
        # Запрос 1: бронирование на те же даты (хочет занять 2-е место)
        # Запрос 2: уменьшение quantity до 1
        booking_task = ac.post(
            "/bookings",
            json={"room_id": room_id, "date_from": "2027-09-01", "date_to": "2027-09-10"},
        )
        patch_task = ac.patch(
            f"/hotels/1/rooms/{room_id}",
            json={"quantity": 1},
        )

        res_book, res_patch = await asyncio.gather(booking_task, patch_task)

        if res_book.status_code == 200 and "data" in res_book.json() and "id" in res_book.json()["data"]:
            created_booking_ids.append(res_book.json()["data"]["id"])

        status_codes = sorted([res_book.status_code, res_patch.status_code])
        # Ровно один запрос успешен (200), а второй отклонён (409)
        assert status_codes == [200, 409]

        # Проверяем инвариант в базе: актуальная пиковая занятость <= актуальное quantity
        room_in_db = await ac.get(f"/hotels/1/rooms/{room_id}")
        assert room_in_db.status_code == 200
        current_quantity = room_in_db.json()["quantity"]

        # Если победило бронирование: броней стало 2, quantity осталось 2 (2 <= 2)
        # Если победил PATCH: quantity стало 1, бронь осталась 1 (1 <= 1)
        actual_peak = await db.bookings.get_peak_occupancy(room_id=room_id)
        assert actual_peak <= current_quantity
    finally:
        for b_id in created_booking_ids:
            await db.bookings.delete(id=b_id)
        await db.rooms.delete(id=room_id)
        await db.commit()