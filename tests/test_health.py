import asyncio
import sqlite3

import httpx

from app.main import app


def test_health_check_initializes_database_and_returns_status(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "codeadventure.db"
    monkeypatch.setenv("CODEADVENTURE_DB_PATH", str(database_path))

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
    assert versions == [(1,)]
