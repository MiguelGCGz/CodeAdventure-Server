from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from app.database import get_connection, initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    yield


class HealthResponse(BaseModel):
    status: str
    service: str


api_router = APIRouter(prefix="/api/v1")


@api_router.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    with get_connection() as connection:
        connection.execute("SELECT 1").fetchone()
    return HealthResponse(status="ok", service="codeadventure-api")


app = FastAPI(
    title="CodeAdventure API",
    description="API da plataforma educativa CodeAdventure.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(api_router)
