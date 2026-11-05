from fastapi import APIRouter, HTTPException, status, Response
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import PaginationDep, DBDep
from src.api.dependencies import UserIdDep
from src.schemas.users import UserAdd, UserRequestAdd
from src.services.auth import AuthService

router = APIRouter(prefix='/auth', tags=['Авторизация и аутентификация'])


@router.post(
    '/login',
)
async def login_user(
        data: UserRequestAdd,
        response: Response,
        db: DBDep
):
    user = await db.users.get_user_with_hashed_password(email=data.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Пользователь c таким email не зарегистрирован')
    if not AuthService().verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Неправильный email или пароль')
    access_token = AuthService().create_access_token({"user_id": user.id})
    response.set_cookie("access_token", access_token)
    return {"access_token": access_token}


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
    '/me'
)
async def get_me(
        user_id: UserIdDep,
        db: DBDep
):
    user = await db.users.get_one_or_none(id=user_id)

    return user

@router.delete(
    '/logout'
)
async def logout(
    response: Response
):
    response.delete_cookie("access_token")

    return {"ok": True}