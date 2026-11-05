from datetime import date

from fastapi import Query, HTTPException, APIRouter, Body, status
from pathlib import Path
from fastapi_cache.decorator import cache

from src.schemas.hotels import HotelPATCH, HotelAdd
from src.api.dependencies import PaginationDep, DBDep

router = APIRouter(prefix="/hotels", tags=['Отели'])

@router.post("",summary="Добавление отеля")
async def create_hotel(db: DBDep, hotel_data: HotelAdd = Body(openapi_examples={
    '1': {'summary': 'Сочи', 'value': {
        'title': 'Отель сочи 5 звезд у моря', 'location': 'ул.Пушкина'
    }},
    '2': {'summary': 'Тблиси', 'value':{
        'title': 'Отель тбилиси Грузия', 'location': 'ул.Пушкина'
    }}
})
):
    hotel = await db.hotels.add(hotel_data)
    await db.commit()

    return {'ok': True, "data": hotel}

@router.get("",summary="Выбрать отель")
@cache(expire=10 )
async def get_hotels(
        pagination: PaginationDep,
        db: DBDep,
        title: str | None = Query(None, description='Название отеля'),
        location: str | None = Query(None, description='Локация отеля'),
        date_from: date = Query(example="2026-10-03"),
        date_to: date = Query(example="2026-10-10")
):
    per_page = pagination.per_page or 5
    return await db.hotels.get_filtered_by_time(
        date_from=date_from,
        date_to=date_to,
        location=location,
        title=title,
        limit=per_page,
        offset=(per_page * (pagination.page - 1))
    )

@router.get('/{hotel_id}')
async def get_hotel(hotel_id: int, db: DBDep):
    hotel = await db.hotels.get_one_or_none(id=hotel_id)

    if hotel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Hotel not found'
        )

    return hotel



@router.delete('/{hotel_id}', summary="Удаление отеля")
async def delete_hotels(db: DBDep, hotel_id: int = Path()):
    await db.hotels.delete(id=hotel_id)
    await db.commit()

    return {'status': 'ok'}


@router.patch(
    '/{hotel_id}',
    summary="Частичное изменение отеля",
    description="<h1>Тут мы частично обновляем данные об отеле, можно отправить name или title или ничего</h1>"
)
async def patch_hotels(
    hotel_id: int,
    hotel_data: HotelPATCH,
    db: DBDep
):
    await db.hotels.edit(hotel_data,exclude_unset=True, id=hotel_id)
    await db.commit()
    return {'status': 'ok'}


@router.put('/{hotel_id}', summary="Полное изменение отеля")
async def edit_hotel(hotel_id: int, hotel_data: HotelAdd, db: DBDep):
    await db.hotels.edit(hotel_data, id=hotel_id)
    await db.commit()
    return {'status': 'ok'}