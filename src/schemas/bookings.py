from pydantic import BaseModel, ConfigDict
from datetime import date


class BookingAddRequest(BaseModel):
    room_id: int
    date_from: date
    date_to: date

class BookingsAdd(BaseModel):
    user_id: int
    room_id: int
    price: int
    date_from: date
    date_to: date

class Booking(BookingsAdd):
    id: int

    model_config = ConfigDict(from_attributes=True)