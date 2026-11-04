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
