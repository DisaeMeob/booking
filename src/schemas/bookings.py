from pydantic import BaseModel, ConfigDict, model_validator
from datetime import date
from typing import Self


class BookingAddRequest(BaseModel):
    room_id: int
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        today = date.today()
        if self.date_from < today:
            raise ValueError("Дата заезда не может быть в прошлом")
        if self.date_from >= self.date_to:
            raise ValueError("Дата заезда должна быть строго раньше даты выезда")
        return self

class BookingsAdd(BaseModel):
    user_id: int
    room_id: int
    price: int
    date_from: date
    date_to: date

class Booking(BookingsAdd):
    id: int
    total_cost: int

    model_config = ConfigDict(from_attributes=True)