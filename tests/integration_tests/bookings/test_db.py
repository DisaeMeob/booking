from datetime import date

from src.schemas.bookings import BookingsAdd
from utils.db_manager import DBManager


async def test_booking_crud(db: DBManager):
    user_id = (await db.users.get_all())[0].id
    room_id = (await db.rooms.get_all())[0].id
    booking_data = BookingsAdd(
        user_id=user_id,
        room_id=room_id,
        price=12345,
        date_from=date(year=2026, month=12, day=31),
        date_to=date(year=2027, month=1, day=1)
    )
    new_booking = await db.bookings.add(booking_data)
    await db.commit()

    booking = await db.bookings.get_one_or_none(id=new_booking.id)
    assert booking
    assert booking.id == new_booking.id
    assert booking.room_id == new_booking.room_id
    assert booking.user_id == new_booking.user_id
    expected_initial_cost = booking_data.price * (booking_data.date_to - booking_data.date_from).days
    assert new_booking.total_cost == expected_initial_cost
    assert booking.total_cost == expected_initial_cost

    updated_date = date(year=2027, month=1, day=10)
    update_booking_date = BookingsAdd(
        user_id=new_booking.user_id,
        room_id=new_booking.room_id,
        price=5000,
        date_from=date(year=2026, month=12, day=31),
        date_to=updated_date
    )
    await db.bookings.edit(data=update_booking_date, exclude_unset=True, id=new_booking.id)
    await db.commit()
    updated_booking = await db.bookings.get_one_or_none(id=new_booking.id)
    assert updated_booking
    assert updated_booking.date_to == updated_date
    assert updated_booking.price == 5000
    expected_updated_cost = update_booking_date.price * (update_booking_date.date_to - update_booking_date.date_from).days
    assert updated_booking.total_cost == expected_updated_cost

    await db.bookings.delete(id=new_booking.id)
    await db.commit()
    booking = await db.bookings.get_one_or_none(id=new_booking.id)
    assert not booking