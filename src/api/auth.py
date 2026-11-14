from fastapi import APIRouter, HTTPException, status, Response
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import PaginationDep, DBDep
from src.api.dependencies import UserIdDep
from src.config import settings
from src.schemas.users import User, UserAdd, UserRequestAdd, UserRequestLogin
from src.services.auth import AuthService

router = APIRouter(prefix='/auth', tags=['Авторизация и аутентификация'])


@router.post(
    '/login',
)
async def login_user(
        data: UserRequestLogin,
        response: Response,
        db: DBDep
):
    user = await db.users.get_user_with_hashed_password(email=data.email)
    if not user or not AuthService().verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Неправильный email или пароль')
    access_token = AuthService().create_access_token({"user_id": user.id})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        path="/",
        samesite="lax",
        secure=settings.MODE == "PROD",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"ok": True}


@router.post(
    '/register',
)
async def register_user(
        data: UserRequestAdd,
        db: DBDep
):
    hashed_password = AuthService().hash_password(data.password)
    new_user_data = UserAdd(email=data.email, hashed_password=hashed_password)
    try:
        await db.users.add(new_user_data)
        await db.commit()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Пользователь с таким email уже зарегистрирован'
        )

    return {"status": "OK"}


@router.get(
    '/me',
    response_model=User,
)
async def get_me(
        user_id: UserIdDep,
        db: DBDep
):
    user = await db.users.get_one_or_none(id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )

    return user

@router.delete(
    '/logout'
)
async def logout(
    response: Response
):
    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.MODE == "PROD",
    )

    return {"ok": True}