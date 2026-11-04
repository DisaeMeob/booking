from datetime import date
from fastapi import HTTPException, APIRouter, Body, status, Query
from pathlib import Path

from src.schemas.facilities import RoomFacilityAdd
from src.schemas.rooms import RoomPatch, RoomsAdd, RoomsAddRequest, RoomPatchRequest, RoomsAddWithoutFac
from src.api.dependencies import DBDep

router = APIRouter(prefix="/hotels", tags=['Номера'])


@router.get("{hotel_id}/rooms", summary="Выбрать номера")
async def get_rooms(
        hotel_id: int,
        db: DBDep,
        date_from: date = Query(example="2026-10-03"),
        date_to: date = Query(example="2026-10-10")

):
        return await db.rooms.get_filtered_by_time(hotel_id=hotel_id, date_from=date_from, date_to=date_to)


@router.post("/{hotel_id}/rooms",summary="Добавление номера")
async def create_room(db: DBDep, hotel_id, room_data: RoomsAddRequest = Body(openapi_examples={
    "1": {
        "summary": "Комната",
        "value": {
            "title": "Комната",
            "description": "Комната стандартная",
            "price": 10000,
            "quantity": 3,
            "facilities_ids": [1, 2, 3]
        }}
})
):
    _room_data = RoomsAddWithoutFac(hotel_id=hotel_id,**room_data.model_dump(exclude={"facilities_ids"}))

    room = await db.rooms.add(_room_data)

    if room_data.facilities_ids:
        rooms_facilities_data = [RoomFacilityAdd(room_id=room.id,facility_id=f_id)for f_id in room_data.facilities_ids]
        await db.room_facility.add_bulk(rooms_facilities_data)

    await db.commit()

    return {"ok": True, "data": room}


@router.get('/{hotel_id}/rooms/{room_id}', summary="Выбрать номер")
async def get_room(hotel_id: int, room_id: int, db: DBDep):
    room = await db.rooms.get_one_or_none(hotel_id=hotel_id, id=room_id)

    return room


@router.delete('{hotel_id}/rooms/{room_id}', summary="Удаление номера")
async def delete_rooms(db: DBDep, hotel_id:int,  room_id: int = Path()):
    await db.rooms.delete(hotel_id=hotel_id, id=room_id)

    return {'status': 'ok'}


@router.put('{hotel_id}/rooms/{room_id}', summary="Полное изменение номера")
async def edit_room(db: DBDep, hotel_id: int, room_id:int,  room_data: RoomsAddRequest):
    _room_data = RoomsAdd(hotel_id=hotel_id, **room_data.model_dump(exclude={"facilities_ids"}))
    await db.rooms.edit(_room_data, id=room_id)
    await db.room_facility.set_room_facilities(room_id, facilities_ids=room_data.facilities_ids)
    await db.commit()
    return {'status': 'ok'}


@router.patch(
    '/{hotel_id}/rooms/{room_id}',
    summary="Частичное изменение информации номера",
    description="<h1>Тут мы частично обновляем данные об комнате, можно отправить name или title или ничего</h1>"
)
async def patch_rooms(
    db: DBDep,
    hotel_id: int,
    room_id: int,
    room_data: RoomPatchRequest,
):
    _room_data_dict = room_data.model_dump(exclude_unset=True)
    _room_data = RoomPatch(hotel_id=hotel_id, **_room_data_dict)
    await db.rooms.edit(data=_room_data,exclude_unset=True, id=room_id, hotel_id=hotel_id)

    if "facilities_ids" in _room_data_dict:
        await db.room_facility.set_room_facilities(room_id, facilities_ids=_room_data_dict["facilities_ids"])

    await db.commit()
    return {'status': 'ok'}

