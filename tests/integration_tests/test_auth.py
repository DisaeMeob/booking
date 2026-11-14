from datetime import UTC, datetime, timedelta
from httpx import AsyncClient
import jwt
import pytest

from src.config import settings
from src.schemas.users import UserAdd
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
    assert "exp" in payload


async def test_get_user_with_hashed_password_not_found(db: DBManager):
    user = await db.users.get_user_with_hashed_password(email="nonexistent@example.com")

    assert user is None


async def test_login_user_not_found(ac: AsyncClient):
    ac.cookies.clear()
    response = await ac.post(
        "/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "somepassword",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Неправильный email или пароль"
    assert "access_token" not in response.cookies
    assert "set-cookie" not in response.headers


async def test_login_wrong_password_returns_same_401_and_no_cookie(ac: AsyncClient):
    ac.cookies.clear()
    not_found_res = await ac.post(
        "/auth/login",
        json={
            "email": "nonexistent_check@example.com",
            "password": "wrong_password_123",
        },
    )
    wrong_pass_res = await ac.post(
        "/auth/login",
        json={
            "email": "kot@pes.com",
            "password": "wrong_password_123",
        },
    )

    assert not_found_res.status_code == 401
    assert wrong_pass_res.status_code == 401
    assert wrong_pass_res.json()["detail"] == "Неправильный email или пароль"
    assert wrong_pass_res.json()["detail"] == not_found_res.json()["detail"]
    assert "access_token" not in wrong_pass_res.cookies
    assert "set-cookie" not in wrong_pass_res.headers


async def test_register_user_success(ac: AsyncClient, db: DBManager):
    email = "new_user@example.com"
    password = "strong_password_123"

    try:
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
    finally:
        user_to_delete = await db.users.get_user_with_hashed_password(email=email)
        if user_to_delete is not None:
            await db.users.delete(id=user_to_delete.id)
            await db.commit()


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


@pytest.mark.parametrize(
    "invalid_password",
    [
        "",
        "   ",
        "        ",
        "1234567",
        " корот ",
        "a" * 73,
        "я" * 37,
    ],
)
async def test_register_invalid_passwords_return_422(
    ac: AsyncClient,
    db: DBManager,
    invalid_password: str,
):
    email = "invalid_pwd_user@example.com"
    response = await ac.post(
        "/auth/register",
        json={
            "email": email,
            "password": invalid_password,
        },
    )

    assert response.status_code == 422
    user = await db.users.get_user_with_hashed_password(email=email)
    assert user is None


async def test_register_and_login_cyrillic_password_within_72_bytes(
    ac: AsyncClient,
    db: DBManager,
):
    email = "cyrillic_user@example.com"
    # 36 кириллических символов = ровно 72 байта в UTF-8
    password_72_bytes = "Ж" * 36
    assert len(password_72_bytes.encode("utf-8")) == 72

    try:
        reg_res = await ac.post(
            "/auth/register",
            json={"email": email, "password": password_72_bytes},
        )
        assert reg_res.status_code == 200

        # Проверка, что последний символ не был обрезан: 35 символов не подходят
        wrong_login = await ac.post(
            "/auth/login",
            json={"email": email, "password": "Ж" * 35},
        )
        assert wrong_login.status_code == 401

        ok_login = await ac.post(
            "/auth/login",
            json={"email": email, "password": password_72_bytes},
        )
        assert ok_login.status_code == 200
        assert ok_login.json() == {"ok": True}
        assert "access_token" not in ok_login.json()
        assert "access_token" in ok_login.cookies
    finally:
        ac.cookies.clear()
        created = await db.users.get_user_with_hashed_password(email=email)
        if created:
            await db.users.delete(id=created.id)
            await db.commit()


async def test_login_existing_user_with_legacy_short_password_succeeds(
    ac: AsyncClient,
    db: DBManager,
):
    email = "legacy_short_pwd@example.com"
    short_password = "short"
    assert len(short_password) < 8

    hashed = AuthService().hash_password(short_password)
    created_user = await db.users.add(UserAdd(email=email, hashed_password=hashed))
    await db.commit()

    try:
        ac.cookies.clear()
        login_res = await ac.post(
            "/auth/login",
            json={"email": email, "password": short_password},
        )
        assert login_res.status_code == 200
        assert login_res.json() == {"ok": True}
        assert "access_token" not in login_res.json()
        assert "access_token" in login_res.cookies

        me_res = await ac.get("/auth/me")
        assert me_res.status_code == 200
        assert me_res.json()["id"] == created_user.id
        assert me_res.json()["email"] == email
    finally:
        ac.cookies.clear()
        await db.users.delete(id=created_user.id)
        await db.commit()


@pytest.mark.parametrize(
    "long_password",
    [
        "a" * 73,
        "я" * 37,
        "x" * 200,
    ],
)
async def test_login_password_over_72_utf8_bytes_returns_401(
    ac: AsyncClient,
    long_password: str,
):
    ac.cookies.clear()

    res_existing = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": long_password},
    )
    assert res_existing.status_code == 401
    assert res_existing.json()["detail"] == "Неправильный email или пароль"
    assert "access_token" not in res_existing.cookies

    res_unknown = await ac.post(
        "/auth/login",
        json={"email": "unknown_long@example.com", "password": long_password},
    )
    assert res_unknown.status_code == 401
    assert res_unknown.json()["detail"] == "Неправильный email или пароль"
    assert "access_token" not in res_unknown.cookies


async def test_cookie_attributes_and_full_session_lifecycle(
    ac: AsyncClient,
    db: DBManager,
):
    ac.cookies.clear()

    # 1. Вход и проверка атрибутов cookie
    login_res = await ac.post(
        "/auth/login",
        json={"email": "kot@pes.com", "password": "12345678"},
    )
    assert login_res.status_code == 200
    assert login_res.json() == {"ok": True}
    assert "access_token" not in login_res.json()
    assert "access_token" in login_res.cookies
    set_cookie_header = login_res.headers.get("set-cookie", "")
    set_cookie_lower = set_cookie_header.lower()

    assert "access_token=" in set_cookie_header
    assert "httponly" in set_cookie_lower
    assert "samesite=lax" in set_cookie_lower
    assert "path=/" in set_cookie_lower
    expected_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert f"max-age={expected_max_age}" in set_cookie_lower
    assert settings.MODE == "TEST"
    assert "secure" not in set_cookie_lower

    # 2. Запрос GET /auth/me с установленной cookie
    me_res = await ac.get("/auth/me")
    assert me_res.status_code == 200
    me_data = me_res.json()
    user_in_db = await db.users.get_user_with_hashed_password(email="kot@pes.com")
    assert user_in_db is not None
    assert me_data["id"] == user_in_db.id
    assert me_data["email"] == "kot@pes.com"
    assert "hashed_password" not in me_data
    assert "password" not in me_data

    # 3. Выход DELETE /auth/logout и проверка заголовка удаления cookie
    logout_res = await ac.delete("/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json() == {"ok": True}
    logout_cookie_header = logout_res.headers.get("set-cookie", "").lower()
    assert "access_token=" in logout_cookie_header
    assert "max-age=0" in logout_cookie_header
    assert "httponly" in logout_cookie_header
    assert "samesite=lax" in logout_cookie_header
    assert "path=/" in logout_cookie_header
    assert "access_token" not in ac.cookies

    # 4. Повторный GET /auth/me после выхода возвращает 401
    me_after_logout = await ac.get("/auth/me")
    assert me_after_logout.status_code == 401
    assert me_after_logout.json()["detail"] == "Вы не предоставили токен доступа"


async def test_get_me_invalid_jwt_tokens_return_401(ac: AsyncClient):
    ac.cookies.clear()
    now = datetime.now(UTC)

    wrong_sig_token = jwt.encode(
        {"user_id": 1, "exp": now + timedelta(minutes=10)},
        "another_secret_key_that_is_32_bytes_or_longer",
        algorithm=settings.JWT_ALGORITHM,
    )
    expired_token = jwt.encode(
        {"user_id": 1, "exp": now - timedelta(minutes=5)},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    no_exp_token = jwt.encode(
        {"user_id": 1},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    no_user_id_token = AuthService().create_access_token({"role": "admin"})
    str_user_id_token = AuthService().create_access_token({"user_id": "1"})
    none_user_id_token = AuthService().create_access_token({"user_id": None})
    zero_user_id_token = AuthService().create_access_token({"user_id": 0})
    negative_user_id_token = AuthService().create_access_token({"user_id": -5})
    bool_true_user_id_token = AuthService().create_access_token({"user_id": True})
    bool_false_user_id_token = AuthService().create_access_token({"user_id": False})

    invalid_tokens_with_expected_detail = [
        (expired_token, "Срок действия токена истек"),
        (wrong_sig_token, "Неверный токен"),
        (no_exp_token, "Неверный токен"),
        (no_user_id_token, "Неверный токен"),
        (str_user_id_token, "Неверный токен"),
        (none_user_id_token, "Неверный токен"),
        (zero_user_id_token, "Неверный токен"),
        (negative_user_id_token, "Неверный токен"),
        (bool_true_user_id_token, "Неверный токен"),
        (bool_false_user_id_token, "Неверный токен"),
        ("malformed.token.value", "Неверный токен"),
    ]

    try:
        for token, expected_detail in invalid_tokens_with_expected_detail:
            ac.cookies.set("access_token", token)
            res = await ac.get("/auth/me")
            assert res.status_code == 401
            assert res.json()["detail"] == expected_detail
    finally:
        ac.cookies.clear()


async def test_get_me_nonexistent_user_in_db_returns_401(ac: AsyncClient):
    ac.cookies.clear()
    ghost_token = AuthService().create_access_token({"user_id": 999999})

    try:
        ac.cookies.set("access_token", ghost_token)
        res = await ac.get("/auth/me")
        assert res.status_code == 401
        assert res.json()["detail"] == "Пользователь не найден"
    finally:
        ac.cookies.clear()
