from datetime import date

from sqlalchemy import select, func

from src.models.rooms import RoomsOrm
from src.repositories.base import BaseRepository
from src.models.hotels import HotelsOrm
from src.repositories.mappers.mappers import HotelDataMapper
from src.repositories.utils import rooms_ids_for_booking
from src.schemas.hotels import Hotel


class HotelsRepository(BaseRepository):
    model = HotelsOrm
    mapper = HotelDataMapper

    async def get_filtered_by_time(self, date_from: date, date_to: date, location, title, limit, offset) -> list[Hotel]:
        rooms_ids_to_get = rooms_ids_for_booking(date_from=date_from, date_to=date_to)

        hotels_ids_to_get = (
            select(RoomsOrm.hotel_id)
            .select_from(RoomsOrm)
            .filter(RoomsOrm.id.in_(rooms_ids_to_get))
            .limit(limit)
            .offset(offset)
        )

        query = select(HotelsOrm).filter(HotelsOrm.id.in_(hotels_ids_to_get))

        if location:
            query = query.filter(func.lower(HotelsOrm.location).contains(location.strip().lower()))
            # ).filter_by(location=location)
        if title:
            query = query.filter(func.lower(HotelsOrm.title).contains(
                title.strip().lower()))  # .contains делает тоже-самое, что и %%, перевод "содержит", в данном случае лучше,
            # чем ilike, т.к внутри ilike мы прописываем сам title.strip().lower() - то есть приводим к нижнему регистру и пробелы убираем

        query = (
            query
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(query)

        return [self.mapper.map_to_domain_entity(hotel) for hotel in result.scalars().all()]

