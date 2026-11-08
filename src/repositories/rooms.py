from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.repositories.base import BaseRepository
from src.models.rooms import RoomsOrm
from src.repositories.mappers.mappers import RoomDataMapper, RoomDataWithRelMapper
from src.repositories.utils import rooms_ids_for_booking


class RoomsRepository(BaseRepository):
    model = RoomsOrm
    mapper = RoomDataMapper

    async def get_filtered_by_time(self, hotel_id: int, date_from: date, date_to: date):
        rooms_ids_to_get = rooms_ids_for_booking(hotel_id=hotel_id, date_from=date_from, date_to=date_to)

        query = (
            select(self.model)
            .options(joinedload(self.model.facilities))
            .filter(RoomsOrm.id.in_(rooms_ids_to_get))
        )
        result = await self.session.execute(query)

        return [RoomDataWithRelMapper.map_to_domain_entity(model) for model in result.unique().scalars().all()]

    async def get_one_or_none(self, with_for_update: bool = False, **filter_by):
        query = (
            select(self.model)
            .options(joinedload(self.model.facilities))
            .filter_by(**filter_by)
        )
        if with_for_update:
            query = query.with_for_update(of=self.model)

        result = await self.session.execute(query)
        model = result.unique().scalars().one_or_none()

        if model is None:
            return None

        return RoomDataWithRelMapper.map_to_domain_entity(model)

    async def has_rooms_for_hotel(self, hotel_id: int) -> bool:
        query = select(select(self.model.id).filter_by(hotel_id=hotel_id).exists())
        res = await self.session.execute(query)
        return bool(res.scalar())
