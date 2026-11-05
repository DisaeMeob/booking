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