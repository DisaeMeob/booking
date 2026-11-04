from fastapi import APIRouter

from src.schemas.facilities import FacilityAdd
from src.api.dependencies import DBDep

router = APIRouter(prefix="/facilities", tags=['Удобства'])

@router.get("", summary="Получение удобств")
async def get_facilities(db: DBDep):
    facilities = await db.facilities.get_all()

    return facilities


@router.post("", summary="Добавление удобства")
async def create_facility(db: DBDep, facility_data: FacilityAdd):
    facility = await db.facilities.add(facility_data)
    await db.commit()

    return {"Ok": True, "data": facility}
