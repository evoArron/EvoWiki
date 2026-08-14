import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import bcrypt
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.database import User, create_session_factory, find_user, session_dependency

TOKEN_LIFETIME = timedelta(hours=8)
SERVICE_ROOT = Path(__file__).resolve().parent.parent


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    username: str
    role: str


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


def create_app(
    database_path: Path | None = None,
    database_root: Path | None = None,
    jwt_secret: str | None = None,
    initial_admin_username: str | None = None,
    initial_admin_password: str | None = None,
) -> FastAPI:
    database_path = database_path or SERVICE_ROOT / "evowiki.db"
    database_root = database_root or SERVICE_ROOT
    jwt_secret = jwt_secret or required_environment("EVOWIKI_JWT_SECRET")
    initial_admin_username = initial_admin_username or required_environment("EVOWIKI_ADMIN_USERNAME")
    initial_admin_password = initial_admin_password or required_environment("EVOWIKI_ADMIN_PASSWORD")
    session_factory = create_session_factory(database_path, database_root)
    seed_admin(session_factory, initial_admin_username, initial_admin_password)

    app = FastAPI(title="EvoWiki MCP Server")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def get_session() -> Session:
        yield from session_dependency(session_factory)

    def current_user(
        authorization: str | None = Header(default=None),
        session: Session = Depends(get_session),
    ) -> User:
        if not authorization or not authorization.startswith("Bearer "):
            raise unauthorized()
        try:
            payload = jwt.decode(authorization.removeprefix("Bearer "), jwt_secret, algorithms=["HS256"])
            username = payload["sub"]
        except (jwt.InvalidTokenError, KeyError):
            raise unauthorized() from None

        user = find_user(session, username)
        if user is None:
            raise unauthorized()
        return user

    @app.post("/api/auth/login", response_model=TokenResponse)
    def login(credentials: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
        user = find_user(session, credentials.username)
        try:
            password_matches = user is not None and bcrypt.checkpw(credentials.password.encode(), user.password_hash.encode())
        except ValueError:
            password_matches = False
        if user is None or user.role != "admin" or not password_matches:
            raise unauthorized()

        expires_at = datetime.now(UTC) + TOKEN_LIFETIME
        token = jwt.encode({"sub": user.username, "exp": expires_at}, jwt_secret, algorithm="HS256")
        return TokenResponse(access_token=token)

    @app.get("/api/auth/me", response_model=CurrentUserResponse)
    def read_current_user(user: User = Depends(current_user)) -> CurrentUserResponse:
        return CurrentUserResponse(username=user.username, role=user.role)

    return app


def seed_admin(factory: sessionmaker[Session], username: str, password: str) -> None:
    with factory.begin() as session:
        if find_user(session, username) is None:
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            session.add(User(username=username, password_hash=password_hash))


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=os.getenv("EVOWIKI_HOST", "127.0.0.1"),
        port=int(os.getenv("EVOWIKI_PORT", "8000")),
    )


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败",
        headers={"WWW-Authenticate": "Bearer"},
    )
