import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash

from app.database import get_connection


ALGORITHM = "HS256"
ACCESS_TOKEN_LIFETIME = timedelta(minutes=30)
password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class User:
    id: int
    username: str


def _secret_key() -> str:
    secret = os.getenv("CODEADVENTURE_SECRET_KEY")
    if not secret:
        raise RuntimeError("CODEADVENTURE_SECRET_KEY is not configured.")
    return secret


def create_user(username: str, password: str) -> User:
    hashed_password = password_hash.hash(password)
    try:
        with get_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, hashed_password),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        if "UNIQUE constraint failed: users.username" in str(error):
            raise ValueError("Username already exists.") from error
        raise
    if user_id is None:
        raise RuntimeError("User insert did not return an identifier.")
    return User(id=user_id, username=username)


def authenticate_user(username: str, password: str) -> User | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None or not password_hash.verify(password, row["password_hash"]):
        return None
    return User(id=row["id"], username=row["username"])


def create_access_token(user_id: int) -> str:
    expires_at = datetime.now(timezone.utc) + ACCESS_TOKEN_LIFETIME
    return jwt.encode(
        {"sub": str(user_id), "exp": expires_at},
        _secret_key(),
        algorithm=ALGORITHM,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> int:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticação necessária.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials,
            _secret_key(),
            algorithms=[ALGORITHM],
        )
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise unauthorized
        return int(subject)
    except (jwt.InvalidTokenError, ValueError, TypeError) as error:
        raise unauthorized from error
