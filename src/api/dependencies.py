from fastapi import Depends, Query, HTTPException, status
from pydantic import BaseModel
from typing import Annotated
from fastapi import Request

from src.database import async_session_maker
from src.services.auth import AuthService
from src.utils.db_manager import DBManager


class PaginationParams(BaseModel):
    page: Annotated[int | None, Query(1, description='страница', ge=1, le=100)]
    per_page: Annotated[int | None, Query(None, description='за страницу', ge=1, lt=30)]

PaginationDep = Annotated[PaginationParams, Depends()]


def get_token(request: Request) -> str:
    token = request.cookies.get("access_token", None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Вы не предоставили токен доступа")

    return token


def get_current_user_id(token: str = Depends(get_token)) -> int:
    data = AuthService().decode_jwt_token(token)

    return data["user_id"]


UserIdDep = Annotated[int, Depends(get_current_user_id)]


def get_db_manager():
    return DBManager(session_factory=async_session_maker)


async def get_db():
    async with get_db_manager() as db:
        yield db


DBDep = Annotated[DBManager, Depends(get_db)]