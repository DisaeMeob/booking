from pydantic import BaseModel, ConfigDict, Field, field_validator


class FacilityAdd(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=100)


class FacilityPatch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("title", mode="before")
    @classmethod
    def validate_title_not_null(cls, value):
        if value is None:
            raise ValueError("Поле title не может быть null")
        return value


class Facility(FacilityAdd):
    id: int

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class RoomFacilityAdd(BaseModel):
    room_id: int
    facility_id: int


class RoomFacility(RoomFacilityAdd):
    id: int

    model_config = ConfigDict(from_attributes=True)