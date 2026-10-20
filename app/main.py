import os
from sqlite3 import Row
from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator, Literal

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
                   l.objective, l.xp_reward
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
                   l.objective, l.xp_reward,
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
