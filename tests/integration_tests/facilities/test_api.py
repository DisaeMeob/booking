import asyncio
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError

from src.api.facilities import create_facility
from src.repositories.facilities import FacilitiesRepository
from src.schemas.facilities import FacilityAdd
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
