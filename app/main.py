import json
import os
from collections.abc import Sequence
from sqlite3 import Row
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncIterator, Literal

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
)
from app.database import get_connection, initialize_database


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    secret_key = os.getenv("CODEADVENTURE_SECRET_KEY", "")
    if len(secret_key) < 32:
        raise RuntimeError(
            "Set CODEADVENTURE_SECRET_KEY to a random value of at least 32 characters."
        )
    initialize_database()
    yield


Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=32,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class HealthResponse(BaseModel):
    status: str
    service: str


class Credentials(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=False)

    username: Username
    password: Password


class UserResponse(BaseModel):
    id: int
    username: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LevelSummary(BaseModel):
    id: int
    title: str
    objective: str
    xp_reward: int
    challenge_type: Literal["sequence_choice", "path_commands", "coming_soon"]
    status: Literal["available", "locked", "completed"]
    stars: int | None


class WorldSummary(BaseModel):
    id: int
    title: str
    description: str
    icon: str
    theme_color: str
    status: Literal["available", "locked", "completed"]
    completed_levels: int
    total_levels: int
    levels: list[LevelSummary]


class CatalogLevelItem(BaseModel):
    id: int
    title: str
    objective: str
    xp_reward: int
    challenge_type: Literal["sequence_choice", "path_commands", "coming_soon"]


class WorldCatalog(BaseModel):
    id: int
    title: str
    description: str
    icon: str
    theme_color: str
    levels: list[CatalogLevelItem]


class DashboardResponse(BaseModel):
    player: UserResponse
    total_xp: int
    completed_levels: int
    total_levels: int
    progress_percentage: int
    worlds: list[WorldSummary]


class LevelChallengeResponse(BaseModel):
    id: int
    world_id: int
    world_title: str
    title: str
    objective: str
    xp_reward: int
    challenge_type: Literal["sequence_choice", "path_commands", "coming_soon"]
    challenge: dict[str, object]
    completed: bool
    stars: int | None


Direction = Literal["up", "down", "left", "right"]


class LevelSubmission(BaseModel):
    answer: str | list[Direction]


class LevelSubmissionResponse(BaseModel):
    correct: bool
    already_completed: bool
    stars: int | None
    xp_awarded: int
    message: str


api_router = APIRouter(prefix="/api/v1")


def token_response(user: UserResponse) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(user.id), user=user)


@api_router.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    with get_connection() as connection:
        connection.execute("SELECT 1").fetchone()
    return HealthResponse(status="ok", service="codeadventure-api")


@api_router.get("/worlds", response_model=list[WorldCatalog], tags=["worlds"])
def list_worlds() -> list[WorldCatalog]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT w.id AS world_id, w.title AS world_title,
                   w.description, w.icon, w.theme_color,
                   l.id AS level_id, l.title AS level_title,
                   l.objective, l.xp_reward, l.challenge_type
            FROM worlds AS w
            LEFT JOIN levels AS l ON l.world_id = w.id
            ORDER BY w.position, l.position
            """
        ).fetchall()

    catalog: dict[int, WorldCatalog] = {}
    for row in rows:
        world = catalog.get(row["world_id"])
        if world is None:
            world = WorldCatalog(
                id=row["world_id"],
                title=row["world_title"],
                description=row["description"],
                icon=row["icon"],
                theme_color=row["theme_color"],
                levels=[],
            )
            catalog[world.id] = world
        if row["level_id"] is not None:
            world.levels.append(
                CatalogLevelItem(
                    id=row["level_id"],
                    title=row["level_title"],
                    objective=row["objective"],
                    xp_reward=row["xp_reward"],
                    challenge_type=row["challenge_type"],
                )
            )
    return list(catalog.values())


@api_router.post(
    "/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["authentication"],
)
def register(credentials: Credentials) -> TokenResponse:
    try:
        user = create_user(credentials.username, credentials.password)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este nome de utilizador já está registado.",
        ) from error
    return token_response(UserResponse(id=user.id, username=user.username))


@api_router.post(
    "/auth/login",
    response_model=TokenResponse,
    tags=["authentication"],
)
def login(credentials: Credentials) -> TokenResponse:
    user = authenticate_user(credentials.username, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nome de utilizador ou palavra-passe incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_response(UserResponse(id=user.id, username=user.username))


@api_router.get(
    "/users/me",
    response_model=UserResponse,
    tags=["users"],
)
def read_current_user(
    user_id: Annotated[int, Depends(get_current_user)],
) -> UserResponse:
    with get_connection() as connection:
        user = connection.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A sessão já não é válida.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return UserResponse(id=user["id"], username=user["username"])


@api_router.get(
    "/users/me/dashboard",
    response_model=DashboardResponse,
    tags=["users"],
)
def read_dashboard(
    user_id: Annotated[int, Depends(get_current_user)],
) -> DashboardResponse:
    with get_connection() as connection:
        user = connection.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A sessão já não é válida.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        rows = connection.execute(
            """
            SELECT w.id AS world_id, w.title AS world_title,
                   w.description, w.icon, w.theme_color,
                   l.id AS level_id, l.title AS level_title,
                   l.objective, l.xp_reward, l.challenge_type,
                   p.stars, p.xp_awarded
            FROM worlds AS w
            LEFT JOIN levels AS l ON l.world_id = w.id
            LEFT JOIN level_progress AS p
              ON p.level_id = l.id AND p.user_id = ?
            ORDER BY w.position, l.position
            """,
            (user_id,),
        ).fetchall()

    world_rows: dict[int, list[Row]] = {}
    for row in rows:
        world_rows.setdefault(row["world_id"], []).append(row)

    worlds: list[WorldSummary] = []
    previous_world_completed = True
    for world_id, levels in world_rows.items():
        is_unlocked = previous_world_completed
        level_rows: list[LevelSummary] = []
        previous_level_completed = is_unlocked
        completed_count = 0
        for row in levels:
            if row["level_id"] is None:
                continue
            completed = row["stars"] is not None
            if completed:
                completed_count += 1
            level_status: Literal["available", "locked", "completed"]
            if completed:
                level_status = "completed"
            elif previous_level_completed:
                level_status = "available"
            else:
                level_status = "locked"
            level_rows.append(
                LevelSummary(
                    id=row["level_id"],
                    title=row["level_title"],
                    objective=row["objective"],
                    xp_reward=row["xp_reward"],
                    challenge_type=row["challenge_type"],
                    status=level_status,
                    stars=row["stars"],
                )
            )
            previous_level_completed = completed

        level_total = len(level_rows)
        world_completed = level_total > 0 and completed_count == level_total
        world_status: Literal["available", "locked", "completed"]
        if world_completed:
            world_status = "completed"
        elif is_unlocked:
            world_status = "available"
        else:
            world_status = "locked"
        first_row = levels[0]
        worlds.append(
            WorldSummary(
                id=world_id,
                title=first_row["world_title"],
                description=first_row["description"],
                icon=first_row["icon"],
                theme_color=first_row["theme_color"],
                status=world_status,
                completed_levels=completed_count,
                total_levels=level_total,
                levels=level_rows,
            )
        )
        previous_world_completed = world_completed

    total_levels = sum(world.total_levels for world in worlds)
    completed_levels = sum(world.completed_levels for world in worlds)
    total_xp = sum(
        row["xp_awarded"] or 0
        for world_level_rows in world_rows.values()
        for row in world_level_rows
    )
    return DashboardResponse(
        player=UserResponse(id=user["id"], username=user["username"]),
        total_xp=total_xp,
        completed_levels=completed_levels,
        total_levels=total_levels,
        progress_percentage=(
            round(completed_levels / total_levels * 100) if total_levels else 0
        ),
        worlds=worlds,
    )


def _get_accessible_level(user_id: int, level_id: int) -> Row:
    with get_connection() as connection:
        level = connection.execute(
            """
            SELECT l.id, l.world_id, l.position, l.title, l.objective,
                   l.xp_reward, l.challenge_type, l.challenge_json,
                   l.solution_json, w.title AS world_title
            FROM levels AS l
            JOIN worlds AS w ON w.id = l.world_id
            WHERE l.id = ?
            """,
            (level_id,),
        ).fetchone()
        if level is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Desafio não encontrado.")

        previous_level = connection.execute(
            """
            SELECT p.level_id
            FROM levels AS prior
            JOIN worlds AS prior_world ON prior_world.id = prior.world_id
            LEFT JOIN level_progress AS p
              ON p.level_id = prior.id AND p.user_id = ?
            JOIN worlds AS current_world ON current_world.id = ?
            WHERE prior_world.position < current_world.position
               OR (
                   prior_world.position = current_world.position
                   AND prior.position < ?
               )
            ORDER BY prior_world.position DESC, prior.position DESC
            LIMIT 1
            """,
            (user_id, level["world_id"], level["position"]),
        ).fetchone()
        if previous_level is not None and previous_level["level_id"] is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Conclui o desafio anterior para desbloquear este.",
            )
        return level


@api_router.get(
    "/levels/{level_id}",
    response_model=LevelChallengeResponse,
    tags=["levels"],
)
def read_level(
    level_id: int,
    user_id: Annotated[int, Depends(get_current_user)],
) -> LevelChallengeResponse:
    level = _get_accessible_level(user_id, level_id)
    with get_connection() as connection:
        progress = connection.execute(
            """
            SELECT stars FROM level_progress
            WHERE user_id = ? AND level_id = ?
            """,
            (user_id, level_id),
        ).fetchone()
    return LevelChallengeResponse(
        id=level["id"],
        world_id=level["world_id"],
        world_title=level["world_title"],
        title=level["title"],
        objective=level["objective"],
        xp_reward=level["xp_reward"],
        challenge_type=level["challenge_type"],
        challenge=json.loads(level["challenge_json"]),
        completed=progress is not None,
        stars=progress["stars"] if progress is not None else None,
    )


def _path_is_correct(
    answer: Sequence[str],
    challenge: dict[str, object],
) -> bool:
    if not answer or len(answer) > challenge["max_commands"]:
        return False
    rows = challenge["rows"]
    columns = challenge["columns"]
    start = challenge["start"]
    goal = challenge["goal"]
    walls = {tuple(cell) for cell in challenge["walls"]}
    row, column = start
    directions = {
        "up": (-1, 0),
        "down": (1, 0),
        "left": (0, -1),
        "right": (0, 1),
    }
    for index, command in enumerate(answer):
        delta_row, delta_column = directions[command]
        row += delta_row
        column += delta_column
        if (
            row < 0
            or row >= rows
            or column < 0
            or column >= columns
            or (row, column) in walls
        ):
            return False
        if [row, column] == goal and index != len(answer) - 1:
            return False
    return [row, column] == goal


def _check_level_answer(
    level: Row,
    answer: str | list[str],
) -> tuple[bool, int]:
    challenge = json.loads(level["challenge_json"])
    if level["challenge_type"] == "sequence_choice":
        solution = json.loads(level["solution_json"])
        return answer == solution, 3
    if level["challenge_type"] == "path_commands" and isinstance(answer, list):
        correct = _path_is_correct(answer, challenge)
        if not correct:
            return False, 0
        optimal = challenge["optimal_commands"]
        stars = 3 if len(answer) <= optimal else 2 if len(answer) <= optimal + 2 else 1
        return True, stars
    return False, 0


@api_router.post(
    "/levels/{level_id}/submit",
    response_model=LevelSubmissionResponse,
    tags=["levels"],
)
def submit_level(
    level_id: int,
    submission: LevelSubmission,
    user_id: Annotated[int, Depends(get_current_user)],
) -> LevelSubmissionResponse:
    level = _get_accessible_level(user_id, level_id)
    if level["challenge_type"] == "coming_soon":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este desafio ainda não está disponível.",
        )
    correct, stars = _check_level_answer(level, submission.answer)
    if not correct:
        return LevelSubmissionResponse(
            correct=False,
            already_completed=False,
            stars=None,
            xp_awarded=0,
            message="Ainda não! Revê a sequência e tenta outra vez.",
        )

    xp_awarded = {
        3: level["xp_reward"],
        2: round(level["xp_reward"] * 0.7),
        1: round(level["xp_reward"] * 0.4),
    }[stars]
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO level_progress (user_id, level_id, stars, xp_awarded)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (user_id, level_id) DO NOTHING
            """,
            (user_id, level_id, stars, xp_awarded),
        )
        if cursor.rowcount == 0:
            existing = connection.execute(
                """
                SELECT stars FROM level_progress
                WHERE user_id = ? AND level_id = ?
                """,
                (user_id, level_id),
            ).fetchone()
            return LevelSubmissionResponse(
                correct=True,
                already_completed=True,
                stars=existing["stars"],
                xp_awarded=0,
                message="Este desafio já está concluído. As tuas estrelas estão guardadas!",
            )
    return LevelSubmissionResponse(
        correct=True,
        already_completed=False,
        stars=stars,
        xp_awarded=xp_awarded,
        message="Muito bem! Concluíste o desafio e ganhaste experiência.",
    )


app = FastAPI(
    title="CodeAdventure API",
    description="API da plataforma educativa CodeAdventure.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CODEADVENTURE_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/", tags=["service"])
def service_info() -> dict[str, str]:
    return {
        "service": "CodeAdventure API",
        "documentation": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


app.include_router(api_router)
