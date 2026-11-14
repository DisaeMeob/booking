from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from src.schemas.facilities import FacilityAdd, FacilityPatch
from src.api.dependencies import DBDep

router = APIRouter(prefix="/facilities", tags=['Удобства'])

FACILITY_TITLE_CONSTRAINTS = {"uq_facilities_title", "facilities_title_key"}


def _is_facility_title_unique_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    cause = getattr(orig, "__cause__", None)

    sqlstate = (
        getattr(orig, "sqlstate", None)
        or getattr(orig, "pgcode", None)
        or getattr(cause, "sqlstate", None)
    )
    constraint_name = (
        getattr(orig, "constraint_name", None)
        or getattr(cause, "constraint_name", None)
    )
    return sqlstate == "23505" and constraint_name in FACILITY_TITLE_CONSTRAINTS


@router.get("", summary="Получение удобств")
async def get_facilities(db: DBDep):
    facilities = await db.facilities.get_all()

    return facilities


@router.post("", summary="Добавление удобства")
async def create_facility(db: DBDep, facility_data: FacilityAdd):
    existing_facility = await db.facilities.get_one_or_none(title=facility_data.title)
    if existing_facility is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Удобство с таким названием уже существует",
        )

    try:
        facility = await db.facilities.add(facility_data)
        await db.commit()
    except IntegrityError as exc:
        await db.session.rollback()
        if _is_facility_title_unique_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Удобство с таким названием уже существует",
            )
        raise

    return {"Ok": True, "data": facility}


@router.get("/{facility_id}", summary="Получение удобства по ID")
async def get_facility(facility_id: int, db: DBDep):
    facility = await db.facilities.get_one_or_none(id=facility_id)
    if facility is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Удобство не найдено",
        )

    return facility


@router.put("/{facility_id}", summary="Полное изменение удобства")
async def edit_facility(
    facility_id: int,
    facility_data: FacilityAdd,
    db: DBDep,
):
    facility = await db.facilities.get_one_or_none(
        id=facility_id, with_for_update=True
    )
    if facility is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Удобство не найдено",
        )

    if facility_data.title != facility.title:
        existing_facility = await db.facilities.get_one_or_none(
            title=facility_data.title
        )
        if existing_facility is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Удобство с таким названием уже существует",
            )

    try:
        await db.facilities.edit(facility_data, id=facility_id)
        await db.commit()
    except IntegrityError as exc:
        await db.session.rollback()
        if _is_facility_title_unique_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Удобство с таким названием уже существует",
            )
        raise

    return {"status": "ok"}


@router.patch("/{facility_id}", summary="Частичное изменение удобства")
async def patch_facility(
    facility_id: int,
    facility_data: FacilityPatch,
    db: DBDep,
):
    facility = await db.facilities.get_one_or_none(
        id=facility_id, with_for_update=True
    )
    if facility is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Удобство не найдено",
        )

    update_data = facility_data.model_dump(exclude_unset=True)
    if not update_data:
        return {"status": "ok"}

    if facility_data.title != facility.title:
        existing_facility = await db.facilities.get_one_or_none(
            title=facility_data.title
        )
        if existing_facility is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Удобство с таким названием уже существует",
            )

    try:
        await db.facilities.edit(
            facility_data, exclude_unset=True, id=facility_id
        )
        await db.commit()
    except IntegrityError as exc:
        await db.session.rollback()
        if _is_facility_title_unique_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Удобство с таким названием уже существует",
            )
        raise

    return {"status": "ok"}


@router.delete("/{facility_id}", summary="Удаление удобства")
async def delete_facility(facility_id: int, db: DBDep):
    facility = await db.facilities.get_one_or_none(
        id=facility_id, with_for_update=True
    )
    if facility is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Удобство не найдено",
        )

    if await db.room_facility.has_rooms_for_facility(facility_id=facility_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Невозможно удалить удобство, которое привязано к номерам",
        )

    await db.facilities.delete(id=facility_id)
    await db.commit()

    return {"status": "ok"}
