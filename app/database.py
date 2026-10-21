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

INTRODUCTORY_LEVELS = (
    (1, 1, "Encontra o padrão", "Observa a sequência e descobre o elemento que falta."),
    (2, 1, "A caminho do objetivo", "Pensa numa sequência de passos para chegar ao destino."),
    (3, 1, "Escolhe o caminho", "Decide que caminho seguir perante uma situação."),
    (4, 1, "Passos repetidos", "Reconhece uma sequência de passos que se repete."),
    (5, 1, "O primeiro programa", "Organiza blocos para criar uma sequência de instruções."),
    (6, 1, "Olá, JavaScript!", "Descobre como uma instrução visual aparece em código."),
)

LEVEL_CHALLENGES = {
    1: {
        "type": "sequence_choice",
        "challenge": {
            "pattern": ["2", "4", "6", "?"],
            "choices": ["7", "8", "9"],
        },
        "solution": "8",
    },
    2: {
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
    },
}


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
                (world_id, world_id, position, title, objective)
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
