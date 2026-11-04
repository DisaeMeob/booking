from fastapi import APIRouter, HTTPException, status

from src.schemas.bookings import BookingsAdd, BookingAddRequest
from src.api.dependencies import DBDep, UserIdDep

router = APIRouter(prefix="/bookings", tags=['Бронирование'])

@router.get("", summary="Получение бронирований")
async def get_booking(
    db: DBDep
):
    bookings = await db.bookings.get_all()
    bookings_list = []

    for booking in bookings:
        bookings_list.append(
            BookingAddRequest(room_id=booking.room_id, date_from=booking.date_from, date_to=booking.date_to)
        )

    return {"data": bookings_list}

@router.get("/me", summary="Получение своих бронирований")
async def get_my_bookings(
        user_id: UserIdDep,
        db: DBDep,
):
    bookings = await db.bookings.get_filtered(user_id=user_id)

    return {"data": bookings}

@router.post("", summary="Добавление бронирования")
async def add_booking(
        user_id: UserIdDep,
        db: DBDep,
        booking_data: BookingAddRequest
):
    room = await db.rooms.get_one_or_none(id=booking_data.room_id)

    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

    room_price = room.price

    _booking = BookingsAdd(
        user_id=user_id,
        price=room_price,
        **booking_data.dict()
    )
    booking = await db.bookings.add(_booking)
    await db.commit()
    return {"status": "Ok", "data": booking}