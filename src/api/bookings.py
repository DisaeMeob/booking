from fastapi import APIRouter, HTTPException, status

from src.repositories.bookings import RoomNotFoundRepositoryError, RoomFullyBookedRepositoryError
from src.schemas.bookings import BookingAddRequest
from src.api.dependencies import DBDep, UserIdDep

router = APIRouter(prefix="/bookings", tags=['Бронирование'])

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


@router.delete("/{booking_id}", summary="Отмена бронирования")
async def delete_booking(
        booking_id: int,
        user_id: UserIdDep,
        db: DBDep,
):
    is_deleted = await db.bookings.delete_user_booking(booking_id=booking_id, user_id=user_id)
    if not is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Бронирование не найдено",
        )

    await db.commit()
    return {"status": "Ok"}