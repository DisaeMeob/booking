from sqlalchemy import select, delete
from datetime import date

from src.models.bookings import BookingsOrm
from src.models.rooms import RoomsOrm
from src.repositories.base import BaseRepository
from src.repositories.mappers.mappers import BookingDataMapper
from src.repositories.utils import rooms_ids_for_booking
from src.schemas.bookings import BookingAddRequest, BookingsAdd


class RoomNotFoundRepositoryError(Exception):
    pass


class RoomFullyBookedRepositoryError(Exception):
    pass


class BookingsRepository(BaseRepository):
    model = BookingsOrm
    mapper = BookingDataMapper

    async def get_bookings_with_today_checkin(self):
        query = (
            select(BookingsOrm)
            .filter(BookingsOrm.date_from == date.today())
        )
        res = await self.session.execute(query)
        return [self.mapper.map_to_domain_entity(booking) for booking in res.scalars().all()]

    async def add_booking(self, user_id: int, booking_data: BookingAddRequest):
        # 1. Блокируем запись RoomsOrm через SELECT ... FOR UPDATE
        room_query = (
            select(RoomsOrm)
            .filter_by(id=booking_data.room_id)
            .with_for_update()
        )
        room_res = await self.session.execute(room_query)
        room = room_res.scalars().one_or_none()

        if room is None:
            raise RoomNotFoundRepositoryError("Номер не найден")

        # 2. Проверяем доступность номера отдельным запросом в рамках той же транзакции
        free_rooms_query = rooms_ids_for_booking(
            date_from=booking_data.date_from,
            date_to=booking_data.date_to,
            hotel_id=room.hotel_id,
        )
        free_rooms_res = await self.session.execute(free_rooms_query)
        free_rooms_ids = free_rooms_res.scalars().all()

        if room.id not in free_rooms_ids:
            raise RoomFullyBookedRepositoryError("Не осталось свободных номеров")

        # 3. Создаём бронирование с актуальной ценой заблокированного номера
        booking_to_add = BookingsAdd(
            user_id=user_id,
            room_id=room.id,
            price=room.price,
            date_from=booking_data.date_from,
            date_to=booking_data.date_to,
        )
        return await self.add(booking_to_add)

    async def get_peak_occupancy(self, room_id: int) -> int:
        query = (
            select(BookingsOrm.date_from, BookingsOrm.date_to)
            .filter(
                BookingsOrm.room_id == room_id,
                BookingsOrm.date_to > date.today(),
            )
        )
        res = await self.session.execute(query)
        booking_intervals = res.all()

        if not booking_intervals:
            return 0

        # Формируем события:
        # выезд: priority = 0 (обрабатывается первым при совпадении дат)
        # заезд: priority = 1
        events: list[tuple[date, int, int]] = []
        for date_from, date_to in booking_intervals:
            events.append((date_to, -1, 0))
            events.append((date_from, 1, 1))

        # Сортируем: сначала по дате, затем по priority (выезд перед заездом)
        events.sort(key=lambda x: (x[0], x[2]))

        peak_occupancy = 0
        current_active = 0
        for _, change, _ in events:
            current_active += change
            if current_active > peak_occupancy:
                peak_occupancy = current_active

        return peak_occupancy

    async def delete_user_booking(self, booking_id: int, user_id: int) -> bool:
        stmt = (
            delete(BookingsOrm)
            .filter_by(id=booking_id, user_id=user_id)
            .returning(BookingsOrm.id)
        )
        res = await self.session.execute(stmt)
        deleted_id = res.scalar_one_or_none()
        return deleted_id is not None
