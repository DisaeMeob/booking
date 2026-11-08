from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from src.schemas.facilities import FacilityAdd
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
