import asyncio
from datetime import date, timedelta
from httpx import AsyncClient


async def test_get_hotels_caching(ac: AsyncClient):
    today = date.today()
    d_from_1 = (today + timedelta(days=100)).isoformat()
    d_to_1 = (today + timedelta(days=105)).isoformat()

    d_from_2 = (today + timedelta(days=110)).isoformat()
    d_to_2 = (today + timedelta(days=115)).isoformat()

    # 1. Первый запрос с датами d_from_1 -> d_to_1: MISS
    response_1 = await ac.get(
        "/hotels",
        params={
            "date_from": d_from_1,
            "date_to": d_to_1,
        },
    )
    assert response_1.status_code == 200
    assert response_1.headers.get("x-fastapi-cache") == "MISS"
    data_1 = response_1.json()

    # 2. Повторный запрос в пределах TTL с параметрами в обратном порядке: HIT, данные совпадают
    response_2 = await ac.get(
        "/hotels",
        params={
            "date_to": d_to_1,
            "date_from": d_from_1,
        },
    )
    assert response_2.status_code == 200
    assert response_2.headers.get("x-fastapi-cache") == "HIT"
    assert response_2.json() == data_1

    # 3. Запрос с другими датами (d_from_2 -> d_to_2): MISS
    response_3 = await ac.get(
        "/hotels",
        params={
            "date_from": d_from_2,
            "date_to": d_to_2,
        },
    )
    assert response_3.status_code == 200
    assert response_3.headers.get("x-fastapi-cache") == "MISS"


async def test_delete_hotel_not_found(ac: AsyncClient):
    response = await ac.delete("/hotels/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Hotel not found"


async def test_delete_hotel_with_rooms_returns_409(ac: AsyncClient):
    response = await ac.delete("/hotels/1")
    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot delete hotel with existing rooms"

    # Проверяем, что отель остался в базе
    get_response = await ac.get("/hotels/1")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == 1


async def test_delete_empty_hotel_success(ac: AsyncClient):
    create_response = await ac.post(
        "/hotels",
        json={"title": "Empty Hotel For Deletion", "location": "Test Location"},
    )
    assert create_response.status_code == 200
    hotel_id = create_response.json()["data"]["id"]

    delete_response = await ac.delete(f"/hotels/{hotel_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"status": "ok"}

    get_response = await ac.get(f"/hotels/{hotel_id}")
    assert get_response.status_code == 404
    assert get_response.json()["detail"] == "Hotel not found"


async def test_concurrent_hotel_delete_and_room_creation(ac: AsyncClient):
    create_hotel_res = await ac.post(
        "/hotels",
        json={"title": "Hotel for Concurrency Test", "location": "Concurrency City"},
    )
    assert create_hotel_res.status_code == 200
    hotel_id = create_hotel_res.json()["data"]["id"]

    delete_task = ac.delete(f"/hotels/{hotel_id}")
    create_room_task = ac.post(
        f"/hotels/{hotel_id}/rooms",
        json={
            "title": "Concurrent Room",
            "description": "Room description",
            "price": 7000,
            "quantity": 2,
            "facilities_ids": [],
        },
    )

    res_delete, res_create = await asyncio.gather(delete_task, create_room_task)

    # Ни один запрос не должен завершиться с кодом 500
    assert res_delete.status_code != 500
    assert res_create.status_code != 500

    status_codes = sorted([res_delete.status_code, res_create.status_code])
    # Возможны только два корректных исхода:
    # 1. Победило удаление: отель удален (200), создание номера отклонено (404)
    # 2. Победило создание номера: комната создана (200), отель нельзя удалить (409)
    assert status_codes in ([200, 404], [200, 409])

    if res_delete.status_code == 200:
        # Удаление победило: отеля нет, комната не должна существовать
        assert res_create.status_code == 404
        hotel_get = await ac.get(f"/hotels/{hotel_id}")
        assert hotel_get.status_code == 404
    else:
        # Создание победило: комната создана, отель существует, удаление отклонено
        assert res_create.status_code == 200
        assert res_delete.status_code == 409
        hotel_get = await ac.get(f"/hotels/{hotel_id}")
        assert hotel_get.status_code == 200
        room_id = res_create.json()["data"]["id"]
        # Очистка созданных ресурсов
        del_room = await ac.delete(f"/hotels/{hotel_id}/rooms/{room_id}")
        assert del_room.status_code == 200
        del_hotel = await ac.delete(f"/hotels/{hotel_id}")
        assert del_hotel.status_code == 200
