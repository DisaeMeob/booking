from datetime import date
from fastapi import HTTPException, APIRouter, Body, status, Query, Path
from sqlalchemy.exc import IntegrityError

from src.schemas.facilities import RoomFacilityAdd
from src.schemas.rooms import RoomPatch, RoomsAdd, RoomsAddRequest, RoomPatchRequest, RoomsAddWithoutFac
from src.api.dependencies import DBDep

router = APIRouter(prefix="/hotels", tags=['Номера'])


@router.get("/{hotel_id}/rooms", summary="Выбрать номера")
async def get_rooms(
        hotel_id: int,
        db: DBDep,
        date_from: date = Query(examples=["2026-10-03"]),
        date_to: date = Query(examples=["2026-10-10"])

):
        return await db.rooms.get_filtered_by_time(hotel_id=hotel_id, date_from=date_from, date_to=date_to)


async def _validate_facilities_ids(db: DBDep, facilities_ids: list[int]) -> None:
    if not facilities_ids:
        return
    existing_ids = await db.facilities.get_by_ids(facilities_ids, with_for_update=True)
    missing_ids = sorted(list(set(facilities_ids) - set(existing_ids)))
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Facilities with ids {missing_ids} do not exist",
        )


@router.post(
    "/{hotel_id}/rooms",
    summary="Добавление номера",
    description="Добавление номера в отель. Для привязки удобств (facilities_ids) необходимо предварительно получить реальные ID через GET /facilities.",
)
async def create_room(
    db: DBDep,
    hotel_id: int,
    room_data: RoomsAddRequest = Body(
        openapi_examples={
            "1": {
                "summary": "Комната",
                "value": {
                    "title": "Комната",
                    "description": "Комната стандартная",
                    "price": 10000,
                    "quantity": 3,
                    "facilities_ids": [],
                },
            }
        }
    ),
):
    hotel = await db.hotels.get_one_or_none(id=hotel_id, with_for_update=True)
    if hotel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hotel not found",
        )

    await _validate_facilities_ids(db, room_data.facilities_ids)

    _room_data = RoomsAddWithoutFac(hotel_id=hotel_id, **room_data.model_dump(exclude={"facilities_ids"}))

    room = await db.rooms.add(_room_data)

    if room_data.facilities_ids:
        unique_facilities_ids = list(dict.fromkeys(room_data.facilities_ids))
        rooms_facilities_data = [RoomFacilityAdd(room_id=room.id, facility_id=f_id) for f_id in unique_facilities_ids]
        await db.room_facility.add_bulk(rooms_facilities_data)

    await db.commit()

    return {"ok": True, "data": room}


@router.get('/{hotel_id}/rooms/{room_id}', summary="Выбрать номер")
async def get_room(hotel_id: int, room_id: int, db: DBDep):
    room = await db.rooms.get_one_or_none(hotel_id=hotel_id, id=room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    return room


@router.delete('/{hotel_id}/rooms/{room_id}', summary="Удаление номера")
async def delete_rooms(db: DBDep, hotel_id: int, room_id: int = Path()):
    room = await db.rooms.get_one_or_none(hotel_id=hotel_id, id=room_id, with_for_update=True)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    if await db.bookings.has_bookings_for_room(room_id=room_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete room with existing bookings",
        )

    try:
        await db.room_facility.delete(room_id=room_id)
        await db.rooms.delete(hotel_id=hotel_id, id=room_id)
        await db.commit()
    except IntegrityError as exc:
        await db.session.rollback()
        if "booking" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete room with existing bookings",
            )
        raise exc

    return {'status': 'ok'}


@router.put('/{hotel_id}/rooms/{room_id}', summary="Полное изменение номера")
async def edit_room(db: DBDep, hotel_id: int, room_id:int,  room_data: RoomsAddRequest):
    room = await db.rooms.get_one_or_none(hotel_id=hotel_id, id=room_id, with_for_update=True)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    await _validate_facilities_ids(db, room_data.facilities_ids)

    if room_data.quantity < room.quantity:
        peak_occupancy = await db.bookings.get_peak_occupancy(room_id=room_id)
        if room_data.quantity < peak_occupancy:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Невозможно уменьшить количество номеров до {room_data.quantity}: "
                       f"на выбранные даты уже существует {peak_occupancy} активных бронирований",
            )

    _room_data = RoomsAdd(hotel_id=hotel_id, **room_data.model_dump(exclude={"facilities_ids"}))
    await db.rooms.edit(_room_data, id=room_id, hotel_id=hotel_id)
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
    _raw_fields_dict = room_data.model_dump(exclude_unset=True)

    if "quantity" in _raw_fields_dict and _raw_fields_dict["quantity"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Количество номеров (quantity) не может быть null",
        )

    quantity_is_present = "quantity" in _raw_fields_dict
    facilities_is_present = "facilities_ids" in _raw_fields_dict

    room = await db.rooms.get_one_or_none(
        hotel_id=hotel_id,
        id=room_id,
        with_for_update=quantity_is_present or facilities_is_present,
    )
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )

    if facilities_is_present:
        await _validate_facilities_ids(db, _raw_fields_dict["facilities_ids"])

    if quantity_is_present and _raw_fields_dict["quantity"] < room.quantity:
        new_quantity = _raw_fields_dict["quantity"]
        peak_occupancy = await db.bookings.get_peak_occupancy(room_id=room_id)
        if new_quantity < peak_occupancy:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Невозможно уменьшить количество номеров до {new_quantity}: "
                       f"на выбранные даты уже существует {peak_occupancy} активных бронирований",
            )

    _room_fields_dict = room_data.model_dump(exclude_unset=True, exclude={"facilities_ids"})
    if _room_fields_dict:
        _room_data = RoomPatch(hotel_id=hotel_id, **_room_fields_dict)
        await db.rooms.edit(data=_room_data, exclude_unset=True, id=room_id, hotel_id=hotel_id)

    if "facilities_ids" in _raw_fields_dict:
        await db.room_facility.set_room_facilities(room_id, facilities_ids=_raw_fields_dict["facilities_ids"])

    await db.commit()
    return {'status': 'ok'}

