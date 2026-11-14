import asyncio
from time import monotonic
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.api.facilities import create_facility
from src.database import async_session_maker_null_pool
from src.models.facilities import RoomsFacilitiesOrm
from src.repositories.facilities import FacilitiesRepository
from src.repositories.mappers.mappers import RoomFacilityDataMapper
from src.schemas.facilities import FacilityAdd, RoomFacility, RoomFacilityAdd
from src.schemas.hotels import HotelAdd
from src.schemas.rooms import RoomsAdd
from src.utils.db_manager import DBManager


async def test_create_facility_unique_title_succeeds(ac: AsyncClient, db: DBManager):
    facility_id = None
    title = "Unique Facility Wi-Fi Test"
    try:
        response = await ac.post(
            "/facilities",
            json={"title": title},
        )
        if response.status_code == 200:
            facility_id = response.json().get("data", {}).get("id")
        assert response.status_code == 200
        body = response.json()
        assert body["Ok"] is True
        assert body["data"]["title"] == title
        assert facility_id is not None

        fac_in_db = await db.facilities.get_one_or_none(id=facility_id)
        assert fac_in_db is not None
        assert fac_in_db.title == title
    finally:
        if facility_id is not None:
            await db.facilities.delete(id=facility_id)
            await db.commit()


async def test_create_facility_duplicate_title_returns_409(ac: AsyncClient, db: DBManager):
    facility_id = None
    title = "Duplicate Facility Parking Test"
    try:
        first_res = await ac.post(
            "/facilities",
            json={"title": title},
        )
        if first_res.status_code == 200:
            facility_id = first_res.json().get("data", {}).get("id")
        assert first_res.status_code == 200
        assert facility_id is not None

        second_res = await ac.post(
            "/facilities",
            json={"title": title},
        )
        assert second_res.status_code == 409
        assert second_res.json() == {
            "detail": "Удобство с таким названием уже существует"
        }
    finally:
        if facility_id is not None:
            await db.facilities.delete(id=facility_id)
            await db.commit()


async def test_create_facility_integrity_error_on_save_returns_409_and_session_recovers(
    ac: AsyncClient, db: DBManager
):
    first_facility = None
    second_facility_id = None
    next_api_facility_id = None
    duplicate_title = "Race Condition Facility Pool Test"
    next_title = "Recovered Session Facility Spa Test"
    next_api_title = "Recovered API Facility Gym Test"

    try:
        first_facility = await db.facilities.add(FacilityAdd(title=duplicate_title))
        await db.commit()

        # Имитируем гонку: предварительная проверка get_one_or_none возвращает None,
        # поэтому выполнение гарантированно доходит до INSERT и вызывает реальный
        # IntegrityError (SQLSTATE 23505) от PostgreSQL внутри create_facility.
        with patch.object(
            FacilitiesRepository,
            "get_one_or_none",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_facility(
                    db=db,
                    facility_data=FacilityAdd(title=duplicate_title),
                )

            assert exc_info.value.status_code == 409
            assert exc_info.value.detail == "Удобство с таким названием уже существует"

        # Проверяем, что после rollback() та же самая сессия db осталась работоспособной
        second_res = await create_facility(
            db=db,
            facility_data=FacilityAdd(title=next_title),
        )
        assert second_res["Ok"] is True
        second_facility_id = second_res["data"].id

        # И следующий HTTP POST через клиент также успешно выполняется
        api_res = await ac.post(
            "/facilities",
            json={"title": next_api_title},
        )
        if api_res.status_code == 200:
            next_api_facility_id = api_res.json().get("data", {}).get("id")
        assert api_res.status_code == 200
        assert api_res.json()["data"]["title"] == next_api_title
    finally:
        if next_api_facility_id is not None:
            await db.facilities.delete(id=next_api_facility_id)
        if second_facility_id is not None:
            await db.facilities.delete(id=second_facility_id)
        if first_facility is not None:
            await db.facilities.delete(id=first_facility.id)
        await db.commit()


async def test_create_facility_concurrent_requests_return_200_and_409(
    ac: AsyncClient, db: DBManager
):
    title = "Concurrent Facility Breakfast Test"
    created_ids: list[int] = []
    try:
        res_1, res_2 = await asyncio.gather(
            ac.post("/facilities", json={"title": title}),
            ac.post("/facilities", json={"title": title}),
        )
        for res in (res_1, res_2):
            if res.status_code == 200:
                fac_id = res.json().get("data", {}).get("id")
                if fac_id is not None:
                    created_ids.append(fac_id)

        statuses = sorted([res_1.status_code, res_2.status_code])
        assert statuses == [200, 409]

        conflict_res = res_1 if res_1.status_code == 409 else res_2
        assert conflict_res.json() == {
            "detail": "Удобство с таким названием уже существует"
        }
    finally:
        for fac_id in created_ids:
            await db.facilities.delete(id=fac_id)
        await db.commit()


async def test_create_facility_other_integrity_error_not_converted_to_409(
    db: DBManager,
):
    # Ошибка уникальности другого ограничения (или другой SQLSTATE) не должна маскироваться под 409
    other_pg_exc = asyncpg.exceptions.PostgresError.new(
        {
            "S": "ERROR",
            "C": "23505",
            "M": "duplicate key value violates unique constraint",
            "n": "uq_some_other_table_column",
        }
    )
    fake_integrity_error = IntegrityError(
        statement="INSERT INTO facilities ...",
        params={},
        orig=other_pg_exc,
    )

    with patch.object(
        FacilitiesRepository,
        "add",
        new=AsyncMock(side_effect=fake_integrity_error),
    ):
        with pytest.raises(IntegrityError):
            await create_facility(
                db=db,
                facility_data=FacilityAdd(title="Facility Triggering Other IntegrityError"),
            )


async def test_get_facilities_empty_returns_200_and_empty_list(ac: AsyncClient):
    response = await ac.get("/facilities")
    assert response.status_code == 200
    assert response.json() == []


async def test_get_facilities_returns_all_created_facilities(
    ac: AsyncClient, db: DBManager
):
    created_ids: list[int] = []
    title_1 = "Get All Facility Alpha Test"
    title_2 = "Get All Facility Beta Test"
    try:
        for title in (title_1, title_2):
            res = await ac.post("/facilities", json={"title": title})
            if res.status_code == 200:
                fac_id = res.json().get("data", {}).get("id")
                if fac_id is not None:
                    created_ids.append(fac_id)
            assert res.status_code == 200

        assert len(created_ids) == 2

        get_res = await ac.get("/facilities")
        assert get_res.status_code == 200
        facilities_list = get_res.json()
        assert isinstance(facilities_list, list)

        returned_by_id = {item["id"]: item["title"] for item in facilities_list}
        assert returned_by_id.get(created_ids[0]) == title_1
        assert returned_by_id.get(created_ids[1]) == title_2
    finally:
        for fac_id in created_ids:
            await db.facilities.delete(id=fac_id)
        if created_ids:
            await db.commit()


async def test_create_facility_empty_title_returns_422(ac: AsyncClient):
    response = await ac.post("/facilities", json={"title": ""})
    assert response.status_code == 422


async def test_create_facility_whitespace_only_title_returns_422(ac: AsyncClient):
    response = await ac.post("/facilities", json={"title": "   \t\n  "})
    assert response.status_code == 422


async def test_create_facility_title_101_chars_returns_422(ac: AsyncClient):
    title_101 = "F" * 101
    assert len(title_101) == 101

    response = await ac.post("/facilities", json={"title": title_101})
    assert response.status_code == 422


async def test_create_facility_title_100_chars_succeeds(
    ac: AsyncClient, db: DBManager
):
    facility_id = None
    prefix = "MaxLen100Facility_"
    title_100 = prefix + ("A" * (100 - len(prefix)))
    assert len(title_100) == 100

    try:
        response = await ac.post("/facilities", json={"title": title_100})
        if response.status_code == 200:
            facility_id = response.json().get("data", {}).get("id")
        assert response.status_code == 200
        body = response.json()
        assert body["Ok"] is True
        assert body["data"]["title"] == title_100
        assert len(body["data"]["title"]) == 100
        assert facility_id is not None

        fac_in_db = await db.facilities.get_one_or_none(id=facility_id)
        assert fac_in_db is not None
        assert fac_in_db.title == title_100
    finally:
        if facility_id is not None:
            await db.facilities.delete(id=facility_id)
            await db.commit()


async def test_create_facility_strips_leading_and_trailing_whitespace(
    ac: AsyncClient, db: DBManager
):
    facility_id = None
    clean_title = "Stripped Facility Sauna Test"
    raw_title = f"   {clean_title}   "
    try:
        response = await ac.post("/facilities", json={"title": raw_title})
        if response.status_code == 200:
            facility_id = response.json().get("data", {}).get("id")
        assert response.status_code == 200
        body = response.json()
        assert body["Ok"] is True
        assert body["data"]["title"] == clean_title
        assert facility_id is not None

        fac_in_db = await db.facilities.get_one_or_none(id=facility_id)
        assert fac_in_db is not None
        assert fac_in_db.title == clean_title
    finally:
        if facility_id is not None:
            await db.facilities.delete(id=facility_id)
            await db.commit()


async def test_create_facility_duplicate_with_surrounding_whitespace_returns_409(
    ac: AsyncClient, db: DBManager
):
    facility_id = None
    clean_title = "Whitespace Duplicate Lounge Test"
    padded_title = f"  {clean_title} \t "
    try:
        first_res = await ac.post("/facilities", json={"title": clean_title})
        if first_res.status_code == 200:
            facility_id = first_res.json().get("data", {}).get("id")
        assert first_res.status_code == 200
        assert facility_id is not None

        second_res = await ac.post("/facilities", json={"title": padded_title})
        assert second_res.status_code == 409
        assert second_res.json() == {
            "detail": "Удобство с таким названием уже существует"
        }
    finally:
        if facility_id is not None:
            await db.facilities.delete(id=facility_id)
            await db.commit()


async def test_room_facilities_repository_and_mapper(db: DBManager):
    hotel = None
    room = None
    facility = None
    try:
        hotel = await db.hotels.add(
            HotelAdd(title="Mapper Repository Test Hotel", location="Mapper Test City")
        )
        room = await db.rooms.add(
            RoomsAdd(
                hotel_id=hotel.id,
                title="Mapper Repository Test Room",
                description="Room for RoomFacilityDataMapper test",
                price=5000,
                quantity=1,
            )
        )
        facility = await db.facilities.add(
            FacilityAdd(title="Mapper Repository Balcony Test")
        )
        await db.commit()

        created_link = await db.room_facility.add(
            RoomFacilityAdd(room_id=room.id, facility_id=facility.id)
        )
        await db.commit()

        assert isinstance(created_link, RoomFacility)
        assert created_link.id is not None
        assert created_link.room_id == room.id
        assert created_link.facility_id == facility.id

        orm_obj = RoomsFacilitiesOrm(
            id=created_link.id, room_id=room.id, facility_id=facility.id
        )
        domain_obj = RoomFacilityDataMapper.map_to_domain_entity(orm_obj)
        assert isinstance(domain_obj, RoomFacility)
        assert domain_obj == created_link

        persistence_obj = RoomFacilityDataMapper.map_to_persistence_entity(domain_obj)
        assert isinstance(persistence_obj, RoomsFacilitiesOrm)
        assert persistence_obj.id == created_link.id
        assert persistence_obj.room_id == room.id
        assert persistence_obj.facility_id == facility.id

        fetched_one = await db.room_facility.get_one_or_none(id=created_link.id)
        assert isinstance(fetched_one, RoomFacility)
        assert fetched_one == created_link

        fetched_filtered = await db.room_facility.get_filtered(
            room_id=room.id, facility_id=facility.id
        )
        assert fetched_filtered == [created_link]

        await db.room_facility.set_room_facilities(
            room_id=room.id, facilities_ids=[]
        )
        await db.commit()

        after_clear = await db.room_facility.get_filtered(
            room_id=room.id, facility_id=facility.id
        )
        assert after_clear == []
    finally:
        if room is not None:
            await db.room_facility.delete(room_id=room.id)
            await db.rooms.delete(id=room.id)
        if hotel is not None:
            await db.hotels.delete(id=hotel.id)
        if facility is not None:
            await db.facilities.delete(id=facility.id)
        await db.commit()


# --- GET /facilities/{facility_id} ---


async def test_get_facility_by_id_succeeds(ac: AsyncClient, db: DBManager):
    facility = None
    title = "Get By Id Facility Conditioning Test"
    try:
        facility = await db.facilities.add(FacilityAdd(title=title))
        await db.commit()

        response = await ac.get(f"/facilities/{facility.id}")
        assert response.status_code == 200
        assert response.json() == {"id": facility.id, "title": title}
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


async def test_get_facility_by_id_not_found_returns_404(
    ac: AsyncClient, db: DBManager
):
    facility = await db.facilities.add(FacilityAdd(title="Get 404 Deleted Facility"))
    await db.commit()
    missing_id = facility.id
    await db.facilities.delete(id=missing_id)
    await db.commit()

    response = await ac.get(f"/facilities/{missing_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Удобство не найдено"}


# --- PUT /facilities/{facility_id} ---


async def test_put_facility_succeeds(ac: AsyncClient, db: DBManager):
    facility = None
    try:
        facility = await db.facilities.add(FacilityAdd(title="Put Old Title Test"))
        await db.commit()

        new_title = "Put Updated Title Test"
        response = await ac.put(
            f"/facilities/{facility.id}",
            json={"title": f"  {new_title}  "},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        updated = await db.facilities.get_one_or_none(id=facility.id)
        assert updated is not None
        assert updated.title == new_title
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


async def test_put_facility_not_found_returns_404(ac: AsyncClient, db: DBManager):
    facility = await db.facilities.add(FacilityAdd(title="Put 404 Deleted Facility"))
    await db.commit()
    missing_id = facility.id
    await db.facilities.delete(id=missing_id)
    await db.commit()

    response = await ac.put(
        f"/facilities/{missing_id}",
        json={"title": "Put Nonexistent Title"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Удобство не найдено"}


async def test_put_facility_duplicate_title_returns_409(
    ac: AsyncClient, db: DBManager
):
    fac_1 = None
    fac_2 = None
    title_1 = "Put Duplicate Existing Title Test"
    title_2 = "Put Duplicate Target Title Test"
    try:
        fac_1 = await db.facilities.add(FacilityAdd(title=title_1))
        fac_2 = await db.facilities.add(FacilityAdd(title=title_2))
        await db.commit()

        response = await ac.put(
            f"/facilities/{fac_2.id}",
            json={"title": title_1},
        )
        assert response.status_code == 409
        assert response.json() == {
            "detail": "Удобство с таким названием уже существует"
        }

        fac_2_in_db = await db.facilities.get_one_or_none(id=fac_2.id)
        assert fac_2_in_db is not None
        assert fac_2_in_db.title == title_2
    finally:
        if fac_2 is not None:
            await db.facilities.delete(id=fac_2.id)
        if fac_1 is not None:
            await db.facilities.delete(id=fac_1.id)
        await db.commit()


async def test_put_facility_same_own_title_succeeds(ac: AsyncClient, db: DBManager):
    facility = None
    own_title = "Put Own Title Unchanged Test"
    try:
        facility = await db.facilities.add(FacilityAdd(title=own_title))
        await db.commit()

        response = await ac.put(
            f"/facilities/{facility.id}",
            json={"title": f"  {own_title}  "},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.title == own_title
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


@pytest.mark.parametrize("invalid_title", ["", "   \t\n  "])
async def test_put_facility_empty_or_whitespace_returns_422(
    ac: AsyncClient, db: DBManager, invalid_title: str
):
    facility = None
    original_title = "Put Invalid Whitespace Original Test"
    try:
        facility = await db.facilities.add(FacilityAdd(title=original_title))
        await db.commit()

        response = await ac.put(
            f"/facilities/{facility.id}",
            json={"title": invalid_title},
        )
        assert response.status_code == 422

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.title == original_title
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


async def test_put_facility_title_100_chars_succeeds(ac: AsyncClient, db: DBManager):
    facility = None
    prefix = "PutMaxLen100_"
    title_100 = prefix + ("X" * (100 - len(prefix)))
    assert len(title_100) == 100
    try:
        facility = await db.facilities.add(FacilityAdd(title="Put Before 100 Test"))
        await db.commit()

        response = await ac.put(
            f"/facilities/{facility.id}",
            json={"title": title_100},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.title == title_100
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


async def test_put_facility_title_101_chars_returns_422(
    ac: AsyncClient, db: DBManager
):
    facility = None
    original_title = "Put Before 101 Test"
    title_101 = "P" * 101
    assert len(title_101) == 101
    try:
        facility = await db.facilities.add(FacilityAdd(title=original_title))
        await db.commit()

        response = await ac.put(
            f"/facilities/{facility.id}",
            json={"title": title_101},
        )
        assert response.status_code == 422

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.title == original_title
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


# --- PATCH /facilities/{facility_id} ---


async def test_patch_facility_title_succeeds(ac: AsyncClient, db: DBManager):
    facility = None
    try:
        facility = await db.facilities.add(FacilityAdd(title="Patch Old Title Test"))
        await db.commit()

        new_title = "Patch Updated Title Test"
        response = await ac.patch(
            f"/facilities/{facility.id}",
            json={"title": f"  {new_title}  "},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.title == new_title
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


async def test_patch_facility_not_found_returns_404(ac: AsyncClient, db: DBManager):
    facility = await db.facilities.add(FacilityAdd(title="Patch 404 Deleted Facility"))
    await db.commit()
    missing_id = facility.id
    await db.facilities.delete(id=missing_id)
    await db.commit()

    res_empty = await ac.patch(f"/facilities/{missing_id}", json={})
    assert res_empty.status_code == 404
    assert res_empty.json() == {"detail": "Удобство не найдено"}

    res_with_title = await ac.patch(
        f"/facilities/{missing_id}", json={"title": "New Title"}
    )
    assert res_with_title.status_code == 404
    assert res_with_title.json() == {"detail": "Удобство не найдено"}


async def test_patch_facility_duplicate_title_returns_409(
    ac: AsyncClient, db: DBManager
):
    fac_1 = None
    fac_2 = None
    title_1 = "Patch Duplicate Existing Title Test"
    title_2 = "Patch Duplicate Target Title Test"
    try:
        fac_1 = await db.facilities.add(FacilityAdd(title=title_1))
        fac_2 = await db.facilities.add(FacilityAdd(title=title_2))
        await db.commit()

        response = await ac.patch(
            f"/facilities/{fac_2.id}",
            json={"title": title_1},
        )
        assert response.status_code == 409
        assert response.json() == {
            "detail": "Удобство с таким названием уже существует"
        }

        fac_2_in_db = await db.facilities.get_one_or_none(id=fac_2.id)
        assert fac_2_in_db is not None
        assert fac_2_in_db.title == title_2
    finally:
        if fac_2 is not None:
            await db.facilities.delete(id=fac_2.id)
        if fac_1 is not None:
            await db.facilities.delete(id=fac_1.id)
        await db.commit()


async def test_patch_facility_empty_body_succeeds_without_changes(
    ac: AsyncClient, db: DBManager
):
    facility = None
    original_title = "Patch Empty Body Keeps Title Test"
    try:
        facility = await db.facilities.add(FacilityAdd(title=original_title))
        await db.commit()

        response = await ac.patch(f"/facilities/{facility.id}", json={})
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.title == original_title
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


async def test_patch_facility_null_title_returns_422(
    ac: AsyncClient, db: DBManager
):
    facility = None
    original_title = "Patch Null Title Original Test"
    try:
        facility = await db.facilities.add(FacilityAdd(title=original_title))
        await db.commit()

        response = await ac.patch(
            f"/facilities/{facility.id}",
            json={"title": None},
        )
        assert response.status_code == 422

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.title == original_title
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


@pytest.mark.parametrize("invalid_title", ["", "   \t\n  "])
async def test_patch_facility_empty_or_whitespace_returns_422(
    ac: AsyncClient, db: DBManager, invalid_title: str
):
    facility = None
    original_title = "Patch Invalid Whitespace Original Test"
    try:
        facility = await db.facilities.add(FacilityAdd(title=original_title))
        await db.commit()

        response = await ac.patch(
            f"/facilities/{facility.id}",
            json={"title": invalid_title},
        )
        assert response.status_code == 422

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.title == original_title
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


async def test_patch_facility_title_100_chars_succeeds(
    ac: AsyncClient, db: DBManager
):
    facility = None
    prefix = "PatchMaxLen100_"
    title_100 = prefix + ("Y" * (100 - len(prefix)))
    assert len(title_100) == 100
    try:
        facility = await db.facilities.add(FacilityAdd(title="Patch Before 100 Test"))
        await db.commit()

        response = await ac.patch(
            f"/facilities/{facility.id}",
            json={"title": title_100},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.title == title_100
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


async def test_patch_facility_title_101_chars_returns_422(
    ac: AsyncClient, db: DBManager
):
    facility = None
    original_title = "Patch Before 101 Test"
    title_101 = "Q" * 101
    assert len(title_101) == 101
    try:
        facility = await db.facilities.add(FacilityAdd(title=original_title))
        await db.commit()

        response = await ac.patch(
            f"/facilities/{facility.id}",
            json={"title": title_101},
        )
        assert response.status_code == 422

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.title == original_title
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


async def test_patch_facility_same_own_title_succeeds(
    ac: AsyncClient, db: DBManager
):
    facility = None
    own_title = "Patch Own Title Unchanged Test"
    try:
        facility = await db.facilities.add(FacilityAdd(title=own_title))
        await db.commit()

        response = await ac.patch(
            f"/facilities/{facility.id}",
            json={"title": f"  {own_title}  "},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.title == own_title
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


# --- DELETE /facilities/{facility_id} ---


async def test_delete_unused_facility_succeeds(ac: AsyncClient, db: DBManager):
    facility = None
    try:
        facility = await db.facilities.add(
            FacilityAdd(title="Delete Unused Facility Test")
        )
        await db.commit()

        del_res = await ac.delete(f"/facilities/{facility.id}")
        assert del_res.status_code == 200
        assert del_res.json() == {"status": "ok"}

        get_res = await ac.get(f"/facilities/{facility.id}")
        assert get_res.status_code == 404

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is None
        facility = None
    finally:
        if facility is not None:
            await db.facilities.delete(id=facility.id)
            await db.commit()


async def test_delete_facility_not_found_returns_404(
    ac: AsyncClient, db: DBManager
):
    facility = await db.facilities.add(
        FacilityAdd(title="Delete 404 Deleted Facility")
    )
    await db.commit()
    missing_id = facility.id
    await db.facilities.delete(id=missing_id)
    await db.commit()

    response = await ac.delete(f"/facilities/{missing_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Удобство не найдено"}


async def test_delete_used_facility_returns_409_and_preserves_all_data(
    ac: AsyncClient, db: DBManager
):
    hotel = None
    room = None
    facility = None
    try:
        hotel = await db.hotels.add(
            HotelAdd(title="Delete 409 Hotel", location="Delete 409 City")
        )
        room = await db.rooms.add(
            RoomsAdd(
                hotel_id=hotel.id,
                title="Delete 409 Room",
                description="Room linked to facility",
                price=4000,
                quantity=2,
            )
        )
        facility = await db.facilities.add(
            FacilityAdd(title="Delete Used Facility 409 Test")
        )
        await db.commit()

        await db.room_facility.add(
            RoomFacilityAdd(room_id=room.id, facility_id=facility.id)
        )
        await db.commit()

        del_res = await ac.delete(f"/facilities/{facility.id}")
        assert del_res.status_code == 409
        assert del_res.json() == {
            "detail": "Невозможно удалить удобство, которое привязано к номерам"
        }

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        assert fac_in_db.id == facility.id

        room_in_db = await db.rooms.get_one_or_none(id=room.id)
        assert room_in_db is not None
        assert room_in_db.id == room.id

        links_in_db = await db.room_facility.get_filtered(
            room_id=room.id, facility_id=facility.id
        )
        assert len(links_in_db) == 1
    finally:
        if room is not None:
            await db.room_facility.delete(room_id=room.id)
            await db.rooms.delete(id=room.id)
        if hotel is not None:
            await db.hotels.delete(id=hotel.id)
        if facility is not None:
            await db.facilities.delete(id=facility.id)
        await db.commit()


# --- Детерминированные конкурентные сценарии (2 независимые транзакции) ---


async def _wait_until_blocked_by(
    blocker_pid: int, timeout: float = 3.0
) -> list[int]:
    """Ожидает появления в pg_stat_activity процесса, заблокированного blocker_pid."""
    deadline = monotonic() + timeout
    query = text(
        """
        SELECT pid
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND wait_event_type = 'Lock'
          AND :blocker_pid = ANY(pg_blocking_pids(pid))
        """
    )
    while monotonic() < deadline:
        async with DBManager(session_factory=async_session_maker_null_pool) as db_monitor:
            res = await db_monitor.session.execute(
                query, {"blocker_pid": blocker_pid}
            )
            blocked_pids = list(res.scalars().all())
            if blocked_pids:
                return blocked_pids
        await asyncio.sleep(0.02)

    raise TimeoutError(
        f"Запрос не перешёл в ожидание блокировки PostgreSQL от PID {blocker_pid} за {timeout}с"
    )


async def test_concurrent_attach_locks_first_then_delete_facility_returns_409(
    ac: AsyncClient, db: DBManager
):
    hotel = None
    room = None
    facility = None
    delete_task = None
    try:
        hotel = await db.hotels.add(
            HotelAdd(title="Concurrent Attach First Hotel", location="Lock City")
        )
        room = await db.rooms.add(
            RoomsAdd(
                hotel_id=hotel.id,
                title="Concurrent Attach First Room",
                description="Room",
                price=5000,
                quantity=2,
            )
        )
        facility = await db.facilities.add(
            FacilityAdd(title="Concurrent Attach First Facility Test")
        )
        await db.commit()

        async with DBManager(session_factory=async_session_maker_null_pool) as db_tx1:
            locked_ids = await db_tx1.facilities.get_by_ids(
                [facility.id], with_for_update=True
            )
            assert locked_ids == [facility.id]
            await db_tx1.room_facility.add(
                RoomFacilityAdd(room_id=room.id, facility_id=facility.id)
            )
            blocker_pid = (
                await db_tx1.session.execute(text("SELECT pg_backend_pid()"))
            ).scalar_one()

            # Транзакция B пытается удалить удобство, пока транзакция A держит FOR UPDATE
            delete_task = asyncio.create_task(ac.delete(f"/facilities/{facility.id}"))
            blocked_pids = await _wait_until_blocked_by(blocker_pid, timeout=3.0)
            assert len(blocked_pids) >= 1
            assert not delete_task.done()

            await db_tx1.commit()

        delete_res = await asyncio.wait_for(delete_task, timeout=5.0)
        assert delete_res.status_code == 409
        assert delete_res.json() == {
            "detail": "Невозможно удалить удобство, которое привязано к номерам"
        }

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is not None
        links_in_db = await db.room_facility.get_filtered(
            room_id=room.id, facility_id=facility.id
        )
        assert len(links_in_db) == 1
    finally:
        if delete_task is not None and not delete_task.done():
            delete_task.cancel()
            await asyncio.gather(delete_task, return_exceptions=True)
        if room is not None:
            await db.room_facility.delete(room_id=room.id)
            await db.rooms.delete(id=room.id)
        if hotel is not None:
            await db.hotels.delete(id=hotel.id)
        if facility is not None:
            await db.facilities.delete(id=facility.id)
        await db.commit()


async def test_concurrent_delete_locks_first_then_attach_facility_returns_400(
    ac: AsyncClient, db: DBManager
):
    hotel = None
    room = None
    facility = None
    facility_deleted = False
    put_task = None
    try:
        hotel = await db.hotels.add(
            HotelAdd(title="Concurrent Delete First Hotel", location="Lock City")
        )
        room = await db.rooms.add(
            RoomsAdd(
                hotel_id=hotel.id,
                title="Concurrent Delete First Room",
                description="Room",
                price=5000,
                quantity=2,
            )
        )
        facility = await db.facilities.add(
            FacilityAdd(title="Concurrent Delete First Facility Test")
        )
        await db.commit()

        async with DBManager(session_factory=async_session_maker_null_pool) as db_tx1:
            locked_fac = await db_tx1.facilities.get_one_or_none(
                id=facility.id, with_for_update=True
            )
            assert locked_fac is not None
            assert not await db_tx1.room_facility.has_rooms_for_facility(facility.id)
            await db_tx1.facilities.delete(id=facility.id)
            blocker_pid = (
                await db_tx1.session.execute(text("SELECT pg_backend_pid()"))
            ).scalar_one()

            # Транзакция B пытается привязать удобство к комнате, пока транзакция A держит FOR UPDATE
            put_task = asyncio.create_task(
                ac.put(
                    f"/hotels/{hotel.id}/rooms/{room.id}",
                    json={
                        "title": "Concurrent Delete First Room",
                        "description": "Room",
                        "price": 5000,
                        "quantity": 2,
                        "facilities_ids": [facility.id],
                    },
                )
            )
            blocked_pids = await _wait_until_blocked_by(blocker_pid, timeout=3.0)
            assert len(blocked_pids) >= 1
            assert not put_task.done()

            await db_tx1.commit()
            facility_deleted = True

        put_res = await asyncio.wait_for(put_task, timeout=5.0)
        assert put_res.status_code == 400
        assert put_res.json() == {
            "detail": f"Facilities with ids [{facility.id}] do not exist"
        }

        fac_in_db = await db.facilities.get_one_or_none(id=facility.id)
        assert fac_in_db is None
        links_in_db = await db.room_facility.get_filtered(room_id=room.id)
        assert links_in_db == []
    finally:
        if put_task is not None and not put_task.done():
            put_task.cancel()
            await asyncio.gather(put_task, return_exceptions=True)
        if room is not None:
            await db.room_facility.delete(room_id=room.id)
            await db.rooms.delete(id=room.id)
        if hotel is not None:
            await db.hotels.delete(id=hotel.id)
        if facility is not None and not facility_deleted:
            await db.facilities.delete(id=facility.id)
        await db.commit()


async def test_concurrent_rename_two_facilities_to_same_title_returns_200_and_409(
    ac: AsyncClient, db: DBManager
):
    fac_1 = None
    fac_2 = None
    title_1 = "Concurrent Rename Source One Test"
    title_2 = "Concurrent Rename Source Two Test"
    target_title = "Concurrent Rename Shared Target Test"
    try:
        fac_1 = await db.facilities.add(FacilityAdd(title=title_1))
        fac_2 = await db.facilities.add(FacilityAdd(title=title_2))
        await db.commit()

        res_1, res_2 = await asyncio.wait_for(
            asyncio.gather(
                ac.put(f"/facilities/{fac_1.id}", json={"title": target_title}),
                ac.put(f"/facilities/{fac_2.id}", json={"title": target_title}),
            ),
            timeout=5.0,
        )

        statuses = sorted([res_1.status_code, res_2.status_code])
        assert statuses == [200, 409]

        conflict_res = res_1 if res_1.status_code == 409 else res_2
        assert conflict_res.json() == {
            "detail": "Удобство с таким названием уже существует"
        }

        facilities_with_target = await db.facilities.get_filtered(title=target_title)
        assert len(facilities_with_target) == 1

        fac_1_after = await db.facilities.get_one_or_none(id=fac_1.id)
        fac_2_after = await db.facilities.get_one_or_none(id=fac_2.id)
        assert fac_1_after is not None and fac_2_after is not None
        assert sorted([fac_1_after.title, fac_2_after.title]) in (
            sorted([target_title, title_2]),
            sorted([title_1, target_title]),
        )
    finally:
        if fac_2 is not None:
            await db.facilities.delete(id=fac_2.id)
        if fac_1 is not None:
            await db.facilities.delete(id=fac_1.id)
        await db.commit()


# --- Регрессионный сценарий: создание, изменение и удаление комнаты с удобствами ---


async def test_room_with_facilities_crud_regression(ac: AsyncClient, db: DBManager):
    hotel = None
    fac_1 = None
    fac_2 = None
    room_id = None
    try:
        hotel = await db.hotels.add(
            HotelAdd(title="Regression Room Facilities Hotel", location="Reg City")
        )
        fac_1 = await db.facilities.add(
            FacilityAdd(title="Regression Facility One Test")
        )
        fac_2 = await db.facilities.add(
            FacilityAdd(title="Regression Facility Two Test")
        )
        await db.commit()

        # 1. Создание комнаты с fac_1
        create_res = await ac.post(
            f"/hotels/{hotel.id}/rooms",
            json={
                "title": "Regression Room",
                "description": "Room with facilities",
                "price": 7000,
                "quantity": 3,
                "facilities_ids": [fac_1.id],
            },
        )
        if create_res.status_code == 200:
            room_id = create_res.json().get("data", {}).get("id")
        assert create_res.status_code == 200
        assert room_id is not None

        # 2. Изменение удобств комнаты через PUT (fac_1 -> fac_2)
        put_res = await ac.put(
            f"/hotels/{hotel.id}/rooms/{room_id}",
            json={
                "title": "Regression Room Updated",
                "description": "Room with updated facilities",
                "price": 7500,
                "quantity": 3,
                "facilities_ids": [fac_2.id],
            },
        )
        assert put_res.status_code == 200

        # Пока fac_2 привязан к комнате, удалить его нельзя (409)
        del_fac2_res = await ac.delete(f"/facilities/{fac_2.id}")
        assert del_fac2_res.status_code == 409

        # 3. Изменение удобств комнаты через PATCH (очистка списка удобств)
        patch_res = await ac.patch(
            f"/hotels/{hotel.id}/rooms/{room_id}",
            json={"facilities_ids": []},
        )
        assert patch_res.status_code == 200

        # 4. Привязка обратно fac_1 и удаление комнаты
        patch_attach_res = await ac.patch(
            f"/hotels/{hotel.id}/rooms/{room_id}",
            json={"facilities_ids": [fac_1.id]},
        )
        assert patch_attach_res.status_code == 200

        del_room_res = await ac.delete(f"/hotels/{hotel.id}/rooms/{room_id}")
        assert del_room_res.status_code == 200
        room_id = None

        # После удаления комнаты связь исчезла, оба удобства можно удалить
        links_left = await db.room_facility.get_filtered(facility_id=fac_1.id)
        assert links_left == []
    finally:
        if room_id is not None:
            await db.room_facility.delete(room_id=room_id)
            await db.rooms.delete(id=room_id)
        if hotel is not None:
            await db.hotels.delete(id=hotel.id)
        if fac_2 is not None:
            await db.facilities.delete(id=fac_2.id)
        if fac_1 is not None:
            await db.facilities.delete(id=fac_1.id)
        await db.commit()
