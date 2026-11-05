from fastapi import APIRouter, HTTPException, status

from src.repositories.bookings import RoomNotFoundRepositoryError, RoomFullyBookedRepositoryError
from src.schemas.bookings import BookingAddRequest
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
    try:
        booking = await db.bookings.add_booking(user_id=user_id, booking_data=booking_data)
    except RoomNotFoundRepositoryError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    except RoomFullyBookedRepositoryError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Не осталось свободных номеров на указанные даты",
        )

    await db.commit()
    return {"status": "Ok", "data": booking}