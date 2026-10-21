import asyncio
import json
import sqlite3

import httpx
import pytest

from app.database import (
    WORLD_ONE_PATTERNS,
    WORLD_TWO_ROUTES,
    _level_id,
    initialize_database,
)
from app.main import app


async def _request(
    method: str,
    path: str,
    *,
    json: dict[str, object] | None = None,
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
def player_token(tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("CODEADVENTURE_DB_PATH", str(tmp_path / "levels.db"))
    monkeypatch.setenv("CODEADVENTURE_SECRET_KEY", "test-secret-key-" * 3)
    response = asyncio.run(
        _request(
            "POST",
            "/api/v1/auth/register",
            json={"username": "LevelPlayer", "password": "adventure-pass-1"},
        )
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def api_request(
    method: str,
    path: str,
    *,
    json: dict[str, object] | None = None,
    token: str | None = None,
) -> httpx.Response:
    return asyncio.run(_request(method, path, json=json, token=token))


def route_commands(route: str) -> list[str]:
    directions = {"U": "up", "D": "down", "L": "left", "R": "right"}
    return [directions[step] for step in route]


def test_level_one_returns_playable_sequence_without_solution(
    player_token: str,
) -> None:
    response = api_request("GET", "/api/v1/levels/1", token=player_token)
    result = response.json()

    assert response.status_code == 200
    assert result["challenge_type"] == "sequence_choice"
    assert result["challenge"]["pattern"] == ["2", "4", "6", "?"]
    assert result["challenge"]["choices"] == ["7", "8", "9"]
    assert "solution" not in result


def test_level_two_is_locked_until_previous_level_is_completed(
    player_token: str,
) -> None:
    response = api_request("GET", "/api/v1/levels/2", token=player_token)
    assert response.status_code == 403


def test_level_challenge_requires_authentication() -> None:
    response = api_request("GET", "/api/v1/levels/1")
    assert response.status_code == 401


def test_correct_sequence_awards_xp_once_and_unlocks_world_two(
    player_token: str,
) -> None:
    wrong = api_request(
        "POST",
        "/api/v1/levels/1/submit",
        json={"answer": "7"},
        token=player_token,
    )
    assert wrong.status_code == 200
    assert wrong.json()["correct"] is False
    assert wrong.json()["xp_awarded"] == 0

    correct = api_request(
        "POST",
        "/api/v1/levels/1/submit",
        json={"answer": "8"},
        token=player_token,
    )
    assert correct.status_code == 200
    assert correct.json()["correct"] is True
    assert correct.json()["stars"] == 3
    assert correct.json()["xp_awarded"] == 50

    replay = api_request(
        "POST",
        "/api/v1/levels/1/submit",
        json={"answer": "8"},
        token=player_token,
    )
    assert replay.json()["already_completed"] is True
    assert replay.json()["xp_awarded"] == 0

    next_level = api_request("GET", "/api/v1/levels/102", token=player_token)
    assert next_level.status_code == 200
    assert next_level.json()["challenge_type"] == "sequence_choice"

    dashboard = api_request(
        "GET",
        "/api/v1/users/me/dashboard",
        token=player_token,
    )
    assert dashboard.json()["total_xp"] == 50
    assert dashboard.json()["worlds"][0]["levels"][1]["status"] == "available"
    assert dashboard.json()["worlds"][1]["status"] == "locked"


def test_all_fifteen_pattern_levels_have_distinct_solutions_and_stay_same_type(
    player_token: str,
) -> None:
    assert len(WORLD_ONE_PATTERNS) == 15
    for position, (pattern, answer) in enumerate(WORLD_ONE_PATTERNS, start=1):
        challenge_id = _level_id(1, position)
        response = api_request(
            "GET",
            f"/api/v1/levels/{challenge_id}",
            token=player_token,
        )
        assert response.status_code == 200
        assert response.json()["challenge_type"] == "sequence_choice"
        assert response.json()["challenge"]["pattern"] == pattern
        assert str(answer) in response.json()["challenge"]["choices"]
        assert "solution" not in response.json()
        result = api_request(
            "POST",
            f"/api/v1/levels/{challenge_id}/submit",
            json={"answer": str(answer)},
            token=player_token,
        )
        assert result.status_code == 200
        assert result.json()["correct"] is True, f"Position {position}, route {route}"

    dashboard = api_request(
        "GET",
        "/api/v1/users/me/dashboard",
        token=player_token,
    )
    assert dashboard.json()["worlds"][0]["status"] == "completed"
    assert dashboard.json()["worlds"][1]["status"] == "available"
    assert dashboard.json()["worlds"][1]["levels"][0]["status"] == "available"


def test_all_fifteen_algorithm_levels_are_solvable_and_unlock_next_world(
    player_token: str,
) -> None:
    for position, (_, answer) in enumerate(WORLD_ONE_PATTERNS, start=1):
        api_request(
            "POST",
            f"/api/v1/levels/{_level_id(1, position)}/submit",
            json={"answer": str(answer)},
            token=player_token,
        )

    assert len(WORLD_TWO_ROUTES) == 14
    first_world_two = api_request(
        "POST",
        "/api/v1/levels/2/submit",
        json={"answer": route_commands("RRRUU")},
        token=player_token,
    )
    assert first_world_two.json()["correct"] is True
    first_challenge = api_request("GET", "/api/v1/levels/2", token=player_token)
    challenge_configurations = {
        json.dumps(
            first_challenge.json()["challenge"],
            sort_keys=True,
        )
    }
    assert first_challenge.json()["challenge"]["difficulty"] == 1
    assert first_challenge.json()["challenge"]["optimal_commands"] == 5
    assert len(set(WORLD_TWO_ROUTES)) == 14
    expected_dimensions = ((3, 4), (5, 5), (6, 6), (7, 7), (8, 8))
    expected_steps = (5, 8, 10, 12, 14)
    for position, route in enumerate(WORLD_TWO_ROUTES, start=2):
        level_id = _level_id(2, position)
        response = api_request("GET", f"/api/v1/levels/{level_id}", token=player_token)
        assert response.status_code == 200, f"Position {position}: {response.json()}"
        assert response.json()["challenge_type"] == "path_commands"
        challenge = response.json()["challenge"]
        difficulty = (position - 1) // 3 + 1
        assert challenge["max_commands"] >= len(route)
        assert challenge["optimal_commands"] == len(route)
        assert challenge["difficulty"] == difficulty
        assert (challenge["rows"], challenge["columns"]) == expected_dimensions[difficulty - 1]
        assert len(challenge["walls"]) == difficulty + 1
        assert len(route) == expected_steps[difficulty - 1]
        challenge_configurations.add(
            json.dumps(challenge, sort_keys=True)
        )
        result = api_request(
            "POST",
            f"/api/v1/levels/{level_id}/submit",
            json={"answer": route_commands(route)},
            token=player_token,
        )
        assert result.status_code == 200
        assert result.json()["correct"] is True, f"Position {position}, route {route}"

    assert len(challenge_configurations) == 15
    dashboard = api_request(
        "GET",
        "/api/v1/users/me/dashboard",
        token=player_token,
    )
    assert dashboard.json()["worlds"][1]["status"] == "completed"
    assert dashboard.json()["worlds"][2]["status"] == "available"


def test_algorithm_path_validates_moves_and_awards_stars(
    player_token: str,
) -> None:
    for position, (_, answer) in enumerate(WORLD_ONE_PATTERNS, start=1):
        api_request(
            "POST",
            f"/api/v1/levels/{_level_id(1, position)}/submit",
            json={"answer": str(answer)},
            token=player_token,
        )
    blocked_path = api_request(
        "POST",
        "/api/v1/levels/2/submit",
        json={"answer": ["right", "up", "right", "right", "up"]},
        token=player_token,
    )
    assert blocked_path.status_code == 200
    assert blocked_path.json()["correct"] is False

    solution = api_request(
        "POST",
        "/api/v1/levels/2/submit",
        json={"answer": ["right", "right", "right", "up", "up"]},
        token=player_token,
    )
    assert solution.status_code == 200
    assert solution.json()["correct"] is True
    assert solution.json()["stars"] == 3
    assert solution.json()["xp_awarded"] == 50


def test_existing_database_is_upgraded_without_losing_world_rows(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "older.db"
    monkeypatch.setenv("CODEADVENTURE_DB_PATH", str(database_path))

    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
            INSERT INTO schema_version (version) VALUES (1), (2), (3);
            CREATE TABLE worlds (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                icon TEXT NOT NULL,
                theme_color TEXT NOT NULL,
                position INTEGER NOT NULL UNIQUE
            );
            CREATE TABLE levels (
                id INTEGER PRIMARY KEY,
                world_id INTEGER NOT NULL REFERENCES worlds(id),
                position INTEGER NOT NULL,
                title TEXT NOT NULL,
                objective TEXT NOT NULL,
                xp_reward INTEGER NOT NULL CHECK (xp_reward >= 0),
                UNIQUE (world_id, position)
            );
            INSERT INTO worlds VALUES
                (1, 'Pensamento lógico', 'Lógica', '🧩', 'peach', 1);
            INSERT INTO levels VALUES
                (1, 1, 1, 'Encontra o padrão', 'Descobre o elemento que falta.', 50);
            """
        )

    initialize_database()

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(levels)")
        }
        version = connection.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()[0]
        challenge_type = connection.execute(
            "SELECT challenge_type FROM levels WHERE id = 1"
        ).fetchone()[0]
        world_count = connection.execute("SELECT COUNT(*) FROM worlds").fetchone()[0]

    assert {"challenge_type", "challenge_json", "solution_json"} <= columns
    assert version == 5
    assert challenge_type == "sequence_choice"
    assert world_count == 6
    with sqlite3.connect(database_path) as connection:
        first_world_levels = connection.execute(
            "SELECT COUNT(*) FROM levels WHERE world_id = 1"
        ).fetchone()[0]
        second_world_levels = connection.execute(
            "SELECT COUNT(*) FROM levels WHERE world_id = 2"
        ).fetchone()[0]
    assert first_world_levels == 15
    assert second_world_levels == 15
