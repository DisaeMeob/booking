from httpx import AsyncClient
from src.services.auth import AuthService
from src.utils.db_manager import DBManager


def test_decode_and_encode_access_token():
    data = {"user_id": 1}
    jwt_token = AuthService().create_access_token(data)

    assert jwt_token
    assert isinstance(jwt_token, str)

    payload = AuthService().decode_jwt_token(jwt_token)

    assert payload
    assert payload["user_id"] == data["user_id"]


async def test_get_user_with_hashed_password_not_found(db: DBManager):
    user = await db.users.get_user_with_hashed_password(email="nonexistent@example.com")

    assert user is None


async def test_login_user_not_found(ac: AsyncClient):
    response = await ac.post(
        "/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "somepassword",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Пользователь c таким email не зарегистрирован"
    assert "access_token" not in response.cookies


async def test_register_user_success(ac: AsyncClient, db: DBManager):
    email = "new_user@example.com"
    password = "strong_password_123"

    response = await ac.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "OK"}

    created_user = await db.users.get_user_with_hashed_password(email=email)
    assert created_user is not None
    assert created_user.email == email
    assert created_user.hashed_password != password
    assert AuthService().verify_password(password, created_user.hashed_password)


async def test_register_user_duplicate_email(ac: AsyncClient, db: DBManager):
    email = "kot@pes.com"
    user_before = await db.users.get_user_with_hashed_password(email=email)
    assert user_before is not None

    response = await ac.post(
        "/auth/register",
        json={
            "email": email,
            "password": "new_hacked_password",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Пользователь с таким email уже зарегистрирован"

    users_with_email = await db.users.get_filtered(email=email)
    assert len(users_with_email) == 1

    user_after = await db.users.get_user_with_hashed_password(email=email)
    assert user_after is not None
    assert user_after.id == user_before.id
    assert user_after.email == user_before.email
    assert user_after.hashed_password == user_before.hashed_password
    assert AuthService().verify_password("12345678", user_after.hashed_password)
    assert not AuthService().verify_password("new_hacked_password", user_after.hashed_password)