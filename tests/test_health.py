import asyncio
import sqlite3

import httpx

from app.main import app


def test_health_check_initializes_database_and_returns_status(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "codeadventure.db"
    monkeypatch.setenv("CODEADVENTURE_DB_PATH", str(database_path))
    monkeypatch.setenv("CODEADVENTURE_SECRET_KEY", "test-secret-key-" * 3)

    async def request_health() -> httpx.Response:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                return await client.get("/api/v1/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "codeadventure-api",
    }
    with sqlite3.connect(database_path) as connection:
        versions = connection.execute("SELECT version FROM schema_version").fetchall()
    assert versions == [(1,), (2,), (3,), (4,)]


def test_root_describes_api_and_favicon_is_not_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEADVENTURE_DB_PATH", str(tmp_path / "service.db"))
    monkeypatch.setenv("CODEADVENTURE_SECRET_KEY", "test-secret-key-" * 3)

    async def request_service_info() -> tuple[httpx.Response, httpx.Response]:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                root = await client.get("/")
                favicon = await client.get("/favicon.ico")
                return root, favicon

    root, favicon = asyncio.run(request_service_info())

    assert root.status_code == 200
    assert root.json()["documentation"] == "/docs"
    assert root.json()["health"] == "/api/v1/health"
    assert favicon.status_code == 204
