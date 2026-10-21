import os
import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[1]

WORLD_CATALOG = (
    (1, "Pensamento lógico", "Descobre padrões e resolve desafios de lógica.", "🧩", "peach"),
    (2, "A magia dos algoritmos", "Organiza instruções para chegar ao objetivo.", "🗺️", "blue"),
    (3, "Decisões inteligentes", "Aprende a escolher o que fazer em cada situação.", "🔀", "lilac"),
    (4, "O poder das repetições", "Usa repetições para simplificar instruções.", "🔁", "mint"),
    (5, "Programar com blocos", "Combina blocos visuais para criar programas.", "🧱", "yellow"),
    (6, "Primeiros passos no código", "Relaciona os blocos com código JavaScript.", "💻", "pink"),
)

WORLD_ONE_PATTERNS = (
    (["2", "4", "6", "?"], 8),
    (["5", "10", "15", "?"], 20),
    (["10", "9", "8", "?"], 7),
    (["3", "6", "9", "?"], 12),
    (["1", "3", "5", "?"], 7),
    (["20", "18", "16", "?"], 14),
    (["4", "8", "12", "?"], 16),
    (["7", "14", "21", "?"], 28),
    (["2", "5", "8", "?"], 11),
    (["30", "25", "20", "?"], 15),
    (["1", "2", "4", "8", "?"], 16),
    (["5", "10", "20", "?"], 40),
    (["100", "90", "80", "?"], 70),
    (["6", "9", "12", "?"], 15),
    (["11", "22", "33", "?"], 44),
)

WORLD_TWO_ROUTES = (
    "RRRRUUU",
    "URRRRUU",
    "RURRRUU",
    "RRURRUU",
    "RRRURUU",
    "UURRRRU",
    "URURRRU",
    "RUURRRU",
    "RRUURRU",
    "RRRUURU",
    "DRRRRUUUU",
    "RDRRRUUUU",
    "RRDRRUUUU",
    "RRRDRUUUU",
)

INTRODUCTORY_LEVELS = [
    (1, 1, "Encontra o padrão", "Observa a sequência e descobre o elemento que falta."),
    (2, 1, "A caminho do objetivo", "Pensa numa sequência de passos para chegar ao destino."),
    (3, 1, "Escolhe o caminho", "Decide que caminho seguir perante uma situação."),
    (4, 1, "Passos repetidos", "Reconhece uma sequência de passos que se repete."),
    (5, 1, "O primeiro programa", "Organiza blocos para criar uma sequência de instruções."),
    (6, 1, "Olá, JavaScript!", "Descobre como uma instrução visual aparece em código."),
]

INTRODUCTORY_LEVELS.extend(
    (1, position, f"Padrão numérico {position:02}", "Descobre a regra e escolhe o número que completa o padrão.")
    for position in range(2, 16)
)
INTRODUCTORY_LEVELS.extend(
    (2, position, f"Percurso do explorador {position:02}", "Planeia as instruções para levar o explorador até à estrela.")
    for position in range(2, 16)
)
INTRODUCTORY_LEVELS.sort(key=lambda level: (level[0], level[1]))


def _level_id(world_id: int, position: int) -> int:
    return world_id if position == 1 else world_id * 100 + position


def _pattern_challenge(pattern: list[str], answer: int) -> dict[str, object]:
    return {
        "type": "sequence_choice",
        "challenge": {
            "pattern": pattern,
            "choices": [str(answer - 1), str(answer), str(answer + 1)],
        },
        "solution": str(answer),
    }


def _path_challenge(route: str) -> dict[str, object]:
    directions = {
        "U": (-1, 0),
        "D": (1, 0),
        "L": (0, -1),
        "R": (0, 1),
    }
    row, column = 3, 0
    visited = {(row, column)}
    for direction in route:
        delta_row, delta_column = directions[direction]
        row += delta_row
        column += delta_column
        visited.add((row, column))

    possible_walls = [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3), (3, 1), (3, 2)]
    walls = [cell for cell in possible_walls if cell not in visited][:2]
    return {
        "type": "path_commands",
        "challenge": {
            "rows": 5,
            "columns": 5,
            "start": [3, 0],
            "goal": [0, 4],
            "walls": [list(cell) for cell in walls],
            "max_commands": len(route) + 3,
            "optimal_commands": len(route),
        },
        "solution": None,
        "route": route,
    }


LEVEL_CHALLENGES: dict[int, dict[str, object]] = {}
for position, (pattern, answer) in enumerate(WORLD_ONE_PATTERNS, start=1):
    LEVEL_CHALLENGES[_level_id(1, position)] = _pattern_challenge(pattern, answer)

LEVEL_CHALLENGES[2] = {
    "type": "path_commands",
    "challenge": {
        "rows": 3,
        "columns": 4,
        "start": [2, 0],
        "goal": [0, 3],
        "walls": [[1, 1], [1, 2]],
        "max_commands": 8,
        "optimal_commands": 5,
    },
    "solution": None,
    "route": "RRRUU",
}
for position, route in enumerate(WORLD_TWO_ROUTES, start=2):
    LEVEL_CHALLENGES[_level_id(2, position)] = _path_challenge(route)


def get_database_path() -> Path:
    configured_path = os.getenv("CODEADVENTURE_DB_PATH")
    path = Path(configured_path) if configured_path else PROJECT_ROOT / "data" / "codeadventure.db"
    return path.expanduser().resolve()


@contextmanager
def get_connection(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    database_path = path or get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            yield connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (1)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (2)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worlds (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                icon TEXT NOT NULL,
                theme_color TEXT NOT NULL,
                position INTEGER NOT NULL UNIQUE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS levels (
                id INTEGER PRIMARY KEY,
                world_id INTEGER NOT NULL REFERENCES worlds(id),
                position INTEGER NOT NULL,
                title TEXT NOT NULL,
                objective TEXT NOT NULL,
                xp_reward INTEGER NOT NULL CHECK (xp_reward >= 0),
                challenge_type TEXT NOT NULL DEFAULT 'coming_soon',
                challenge_json TEXT NOT NULL DEFAULT '{}',
                solution_json TEXT NOT NULL DEFAULT 'null',
                UNIQUE (world_id, position)
            )
            """
        )
        level_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(levels)").fetchall()
        }
        for column, definition in (
            ("challenge_type", "TEXT NOT NULL DEFAULT 'coming_soon'"),
            ("challenge_json", "TEXT NOT NULL DEFAULT '{}'"),
            ("solution_json", "TEXT NOT NULL DEFAULT 'null'"),
        ):
            if column not in level_columns:
                connection.execute(
                    f"ALTER TABLE levels ADD COLUMN {column} {definition}"
                )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS level_progress (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                level_id INTEGER NOT NULL REFERENCES levels(id) ON DELETE CASCADE,
                stars INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 3),
                xp_awarded INTEGER NOT NULL CHECK (xp_awarded >= 0),
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, level_id)
            )
            """
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO worlds (id, title, description, icon, theme_color, position)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (world_id, title, description, icon, theme, world_id)
                for world_id, title, description, icon, theme in WORLD_CATALOG
            ),
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO levels (
                id, world_id, position, title, objective, xp_reward
            )
            VALUES (?, ?, ?, ?, ?, 50)
            """,
            (
                (
                    _level_id(world_id, position),
                    world_id,
                    position,
                    title,
                    objective,
                )
                for world_id, position, title, objective in INTRODUCTORY_LEVELS
            ),
        )
        for level_id, configuration in LEVEL_CHALLENGES.items():
            connection.execute(
                """
                UPDATE levels
                SET challenge_type = ?, challenge_json = ?, solution_json = ?
                WHERE id = ?
                """,
                (
                    configuration["type"],
                    json.dumps(configuration["challenge"], ensure_ascii=False),
                    json.dumps(configuration["solution"], ensure_ascii=False),
                    level_id,
                ),
            )
        connection.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (3)"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (4)"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (5)"
        )
