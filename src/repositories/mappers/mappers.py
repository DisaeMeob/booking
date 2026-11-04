from src.models.facilities import FacilitiesOrm
from src.repositories.mappers.base import DataMapper
from src.models.hotels import HotelsOrm
from src.models.rooms import RoomsOrm
from src.models.bookings import BookingsOrm
from src.models.users import UsersOrm

from src.schemas.hotels import Hotel
from src.schemas.rooms import Room, RoomWithRel
from src.schemas.users import User
from src.schemas.facilities import Facility
from src.schemas.bookings import Booking

class HotelDataMapper(DataMapper):
    db_model = HotelsOrm
    schema = Hotel

class RoomDataMapper(DataMapper):
    db_model = RoomsOrm
    schema = Room

class RoomDataWithRelMapper(DataMapper):
    db_model = RoomsOrm
    schema = RoomWithRel


class UserDataMapper(DataMapper):
    db_model = UsersOrm
    schema = User

class BookingDataMapper(DataMapper):
    db_model = BookingsOrm
    schema = Booking

class FacilitiesDataMapper(DataMapper):
    db_model = FacilitiesOrm
    schema = Facility

