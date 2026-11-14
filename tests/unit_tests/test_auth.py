from datetime import UTC, datetime, timedelta
from fastapi import HTTPException
import jwt
import jwt.api_jws as jws
import pytest

from src.api.dependencies import get_current_user_id
from src.config import settings
from src.services.auth import AuthService


def test_create_access_token():
    data = {"user_id": 1}
    jwt_token = AuthService().create_access_token(data)

    assert jwt_token
    assert isinstance(jwt_token, str)

    payload = AuthService().decode_jwt_token(jwt_token)
    assert payload["user_id"] == 1
    assert "exp" in payload


def test_decode_jwt_invalid_signature_raises_401():
    expire = datetime.now(UTC) + timedelta(minutes=10)
    forged_token = jwt.encode(
        {"user_id": 1, "exp": expire},
        "wrong_secret_key_that_is_at_least_32_bytes_long",
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        AuthService().decode_jwt_token(forged_token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Неверный токен"


def test_decode_jwt_expired_raises_401():
    expired = datetime.now(UTC) - timedelta(minutes=5)
    expired_token = jwt.encode(
        {"user_id": 1, "exp": expired},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        AuthService().decode_jwt_token(expired_token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Срок действия токена истек"


def test_decode_jwt_missing_exp_raises_401():
    token_without_exp = jwt.encode(
        {"user_id": 1},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        AuthService().decode_jwt_token(token_without_exp)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Неверный токен"


def test_decode_jwt_malformed_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        AuthService().decode_jwt_token("not-a-valid-jwt")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Неверный токен"


@pytest.mark.parametrize(
    "raw_payload",
    [
        b"123",
        b'"string_payload"',
        b'["list_item"]',
        b"null",
    ],
)
def test_decode_jwt_non_dict_payload_with_valid_signature_raises_401(raw_payload: bytes):
    signed_non_dict_token = jws.encode(
        raw_payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        AuthService().decode_jwt_token(signed_non_dict_token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Неверный токен"


@pytest.mark.parametrize(
    "payload_data",
    [
        {},
        {"user_id": None},
        {"user_id": "1"},
        {"user_id": 1.5},
        {"user_id": 0},
        {"user_id": -10},
        {"user_id": True},
        {"user_id": False},
    ],
)
def test_get_current_user_id_invalid_user_id_raises_401(payload_data: dict):
    token = AuthService().create_access_token(payload_data)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(token=token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Неверный токен"


def test_hash_and_verify_password_utf8_72_byte_limit():
    service = AuthService()
    valid_hash = service.hash_password("valid_password_123")

    with pytest.raises(ValueError, match="72 UTF-8 bytes"):
        service.hash_password("a" * 73)

    with pytest.raises(ValueError, match="72 UTF-8 bytes"):
        service.hash_password("я" * 37)

    assert service.verify_password("a" * 73, valid_hash) is False
    assert service.verify_password("я" * 37, valid_hash) is False
    assert service.verify_password("", valid_hash) is False
    assert service.verify_password("valid_password_123", "not-a-valid-bcrypt-hash") is False
