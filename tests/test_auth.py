import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from app.auth import ALGORITHM
from app.main import app


async def _request(
    method: str,
    path: str,
    *,
    json: dict[str, str] | None = None,
    token: str | None = None,
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.request(method, path, json=json, headers=headers)


@pytest.fixture
def auth_environment(tmp_path, monkeypatch):
    database_path = tmp_path / "auth.db"
    monkeypatch.setenv("CODEADVENTURE_DB_PATH", str(database_path))
    monkeypatch.setenv("CODEADVENTURE_SECRET_KEY", "test-secret-key-" * 3)
    return database_path


def request(
    method: str,
    path: str,
    *,
    json: dict[str, str] | None = None,
    token: str | None = None,
) -> httpx.Response:
    return asyncio.run(_request(method, path, json=json, token=token))


def test_register_login_and_protected_profile(auth_environment) -> None:
    registration = request(
        "POST",
        "/api/v1/auth/register",
        json={"username": "LogicExplorer", "password": "adventure-pass-1"},
    )

    assert registration.status_code == 201
    result = registration.json()
    assert result["user"] == {"id": 1, "username": "LogicExplorer"}
    assert result["token_type"] == "bearer"

    profile = request("GET", "/api/v1/users/me", token=result["access_token"])
    assert profile.status_code == 200
    assert profile.json() == result["user"]

    login = request(
        "POST",
        "/api/v1/auth/login",
        json={"username": "logicexplorer", "password": "adventure-pass-1"},
    )
    assert login.status_code == 200
    assert login.json()["user"] == result["user"]

    with sqlite3.connect(auth_environment) as connection:
        stored_password = connection.execute(
            "SELECT password_hash FROM users WHERE id = 1"
        ).fetchone()[0]
    assert stored_password != "adventure-pass-1"
    assert stored_password.startswith("$argon2")


def test_duplicate_username_is_case_insensitive(auth_environment) -> None:
    credentials = {"username": "Explorer", "password": "adventure-pass-1"}
    assert request("POST", "/api/v1/auth/register", json=credentials).status_code == 201

    duplicate = request(
        "POST",
        "/api/v1/auth/register",
        json={"username": "explorer", "password": "another-pass-2"},
    )
    assert duplicate.status_code == 409


def test_invalid_login_and_missing_token_are_rejected(auth_environment) -> None:
    request(
        "POST",
        "/api/v1/auth/register",
        json={"username": "Explorer", "password": "adventure-pass-1"},
    )
    login = request(
        "POST",
        "/api/v1/auth/login",
        json={"username": "Explorer", "password": "incorrect-pass"},
    )
    profile = request("GET", "/api/v1/users/me")

    assert login.status_code == 401
    assert profile.status_code == 401


def test_expired_token_is_rejected(auth_environment) -> None:
    request(
        "POST",
        "/api/v1/auth/register",
        json={"username": "Explorer", "password": "adventure-pass-1"},
    )
    expired_token = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        },
        "test-secret-key-" * 3,
        algorithm=ALGORITHM,
    )

    response = request("GET", "/api/v1/users/me", token=expired_token)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "credentials",
    [
        {"username": "ab", "password": "adventure-pass-1"},
        {"username": "bad name", "password": "adventure-pass-1"},
        {"username": "Explorer", "password": "short"},
    ],
)
def test_invalid_registration_data_is_rejected(
    auth_environment,
    credentials: dict[str, str],
) -> None:
    response = request("POST", "/api/v1/auth/register", json=credentials)
    assert response.status_code == 422
