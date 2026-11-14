from sqlalchemy import select, delete, insert

from src.models.facilities import FacilitiesOrm, RoomsFacilitiesOrm
from src.repositories.base import BaseRepository
from src.repositories.mappers.mappers import FacilitiesDataMapper, RoomFacilityDataMapper


class FacilitiesRepository(BaseRepository):
    model = FacilitiesOrm
    mapper = FacilitiesDataMapper

    async def get_by_ids(
        self, ids: list[int], with_for_update: bool = False
    ) -> list[int]:
        if not ids:
            return []
        query = select(self.model.id).filter(self.model.id.in_(ids))
        if with_for_update:
            query = query.order_by(self.model.id).with_for_update()
        result = await self.session.execute(query)
        return list(result.scalars().all())


class RoomsFacilitiesRepository(BaseRepository):
    model = RoomsFacilitiesOrm
    mapper = RoomFacilityDataMapper

    async def has_rooms_for_facility(self, facility_id: int) -> bool:
        query = select(
            select(self.model.id).filter_by(facility_id=facility_id).exists()
        )
        res = await self.session.execute(query)
        return bool(res.scalar())

    async def set_room_facilities(self, room_id, facilities_ids: list[int]):
        get_current_facilities_ids = (
            select(self.model.facility_id)
            .filter_by(room_id=room_id)
        )
        result = await self.session.execute(get_current_facilities_ids)
        current_facilities_ids: list[int] = result.scalars().all()

        ids_to_delete: list[int] = list(set(current_facilities_ids) - set(facilities_ids))
        ids_to_insert: list[int] = list(set(facilities_ids) - set(current_facilities_ids))

        if ids_to_delete:
            delete_m2m_facilities = (
                delete(self.model)
                .filter(
                    self.model.room_id == room_id,
                    self.model.facility_id.in_(ids_to_delete)
                        )
            )
            await self.session.execute(delete_m2m_facilities)

        if ids_to_insert:
            insert_m2m_facilities = (
                insert(self.model)
                .values([{"room_id": room_id, "facility_id": f_id} for f_id in ids_to_insert])
            )
            await self.session.execute(insert_m2m_facilities)


