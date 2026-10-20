import os
from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
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


api_router = APIRouter(prefix="/api/v1")


def token_response(user: UserResponse) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(user.id), user=user)


@api_router.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    with get_connection() as connection:
        connection.execute("SELECT 1").fetchone()
    return HealthResponse(status="ok", service="codeadventure-api")


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
app.include_router(api_router)
