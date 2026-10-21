import asyncio
import sqlite3

import httpx
import pytest

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
def dashboard_environment(tmp_path, monkeypatch):
    database_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("CODEADVENTURE_DB_PATH", str(database_path))
    monkeypatch.setenv("CODEADVENTURE_SECRET_KEY", "test-secret-key-" * 3)
    return database_path


def test_new_player_dashboard_shows_seeded_worlds_and_initial_unlock(
    dashboard_environment,
) -> None:
    registration = asyncio.run(
        _request(
            "POST",
            "/api/v1/auth/register",
            json={"username": "MapExplorer", "password": "adventure-pass-1"},
        )
    )
    token = registration.json()["access_token"]

    dashboard = asyncio.run(
        _request("GET", "/api/v1/users/me/dashboard", token=token)
    )
    result = dashboard.json()

    assert dashboard.status_code == 200
    assert result["player"]["username"] == "MapExplorer"
    assert result["total_xp"] == 0
    assert result["completed_levels"] == 0
    assert result["total_levels"] == 34
    assert result["progress_percentage"] == 0
    assert [world["status"] for world in result["worlds"]] == [
        "available",
        "locked",
        "locked",
        "locked",
        "locked",
        "locked",
    ]
    assert result["worlds"][0]["levels"][0]["status"] == "available"
    assert result["worlds"][0]["total_levels"] == 15
    assert result["worlds"][1]["total_levels"] == 15
    assert len(result["worlds"][0]["levels"]) == 15
    assert len(result["worlds"][1]["levels"]) == 15

    with sqlite3.connect(dashboard_environment) as connection:
        world_count = connection.execute("SELECT COUNT(*) FROM worlds").fetchone()[0]
        level_count = connection.execute("SELECT COUNT(*) FROM levels").fetchone()[0]
    assert world_count == 6
    assert level_count == 34


def test_completed_level_awards_only_saved_xp_and_unlocks_next_world(
    dashboard_environment,
) -> None:
    registration = asyncio.run(
        _request(
            "POST",
            "/api/v1/auth/register",
            json={"username": "ProgressPlayer", "password": "adventure-pass-1"},
        )
    )
    token = registration.json()["access_token"]

    with sqlite3.connect(dashboard_environment) as connection:
        connection.execute(
            """
            INSERT INTO level_progress (user_id, level_id, stars, xp_awarded)
            VALUES (1, 1, 2, 35)
            """
        )
        connection.commit()

    response = asyncio.run(
        _request("GET", "/api/v1/users/me/dashboard", token=token)
    )
    result = response.json()

    assert response.status_code == 200
    assert result["total_xp"] == 35
    assert result["completed_levels"] == 1
    assert result["progress_percentage"] == 3
    assert result["worlds"][0]["levels"][0]["stars"] == 2
    assert result["worlds"][0]["status"] == "available"
    assert result["worlds"][0]["levels"][1]["status"] == "available"
    assert result["worlds"][1]["status"] == "locked"


def test_world_catalog_is_public_and_dashboard_requires_authentication(
    dashboard_environment,
) -> None:
    catalog = asyncio.run(_request("GET", "/api/v1/worlds"))
    dashboard = asyncio.run(_request("GET", "/api/v1/users/me/dashboard"))

    assert catalog.status_code == 200
    assert len(catalog.json()) == 6
    assert dashboard.status_code == 401
