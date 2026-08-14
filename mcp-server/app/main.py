import os
import re
from datetime import UTC, datetime, timedelta
from os.path import commonpath
from pathlib import Path

import bcrypt
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database import (
    ProjectPermission,
    User,
    create_session_factory,
    find_project_permission,
    find_user,
    session_dependency,
)

TOKEN_LIFETIME = timedelta(hours=8)
PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SERVICE_ROOT = Path(__file__).resolve().parent.parent
WIKI_ROOT = SERVICE_ROOT.parent / "enterprise-wiki-repo"


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str


class CreateProjectRequest(BaseModel):
    project_id: str


class GrantProjectPermissionRequest(BaseModel):
    username: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    username: str
    role: str


class ProjectResponse(BaseModel):
    project_id: str
    role: str


class TreeNode(BaseModel):
    title: str
    key: str
    is_leaf: bool


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


def create_app(
    database_path: Path | None = None,
    database_root: Path | None = None,
    wiki_root: Path | None = None,
    jwt_secret: str | None = None,
    initial_admin_username: str | None = None,
    initial_admin_password: str | None = None,
) -> FastAPI:
    database_path = database_path or SERVICE_ROOT / "evowiki.db"
    database_root = database_root or SERVICE_ROOT
    wiki_root = wiki_root or WIKI_ROOT
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

    def admin_user(user: User = Depends(current_user)) -> User:
        if user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
        return user

    @app.post("/api/auth/login", response_model=TokenResponse)
    def login(credentials: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
        user = find_user(session, credentials.username)
        try:
            password_matches = user is not None and bcrypt.checkpw(credentials.password.encode(), user.password_hash.encode())
        except ValueError:
            password_matches = False
        if user is None or not password_matches:
            raise unauthorized()

        expires_at = datetime.now(UTC) + TOKEN_LIFETIME
        token = jwt.encode({"sub": user.username, "exp": expires_at}, jwt_secret, algorithm="HS256")
        return TokenResponse(access_token=token)

    @app.get("/api/auth/me", response_model=CurrentUserResponse)
    def read_current_user(user: User = Depends(current_user)) -> CurrentUserResponse:
        return CurrentUserResponse(username=user.username, role=user.role)

    @app.post("/api/admin/users", status_code=status.HTTP_201_CREATED, response_model=CurrentUserResponse)
    def create_user(
        request: CreateUserRequest,
        session: Session = Depends(get_session),
        _: User = Depends(admin_user),
    ) -> CurrentUserResponse:
        if find_user(session, request.username) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
        try:
            password_hash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="密码过长") from None

        user = User(username=request.username, password_hash=password_hash, role="member")
        session.add(user)
        session.commit()
        return CurrentUserResponse(username=user.username, role=user.role)

    @app.post("/api/admin/projects", status_code=status.HTTP_201_CREATED, response_model=ProjectResponse)
    def create_project(
        request: CreateProjectRequest,
        session: Session = Depends(get_session),
        admin: User = Depends(admin_user),
    ) -> ProjectResponse:
        project_path = safe_project_path(wiki_root, request.project_id)
        if project_path.exists():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="项目已存在")

        (project_path / "docs").mkdir(parents=True)
        session.add(ProjectPermission(user_id=admin.id, project_id=request.project_id, role="admin"))
        session.commit()
        return ProjectResponse(project_id=request.project_id, role="admin")

    @app.post("/api/admin/projects/{project_id}/permissions", response_model=ProjectResponse)
    def grant_project_permission(
        project_id: str,
        request: GrantProjectPermissionRequest,
        session: Session = Depends(get_session),
        _: User = Depends(admin_user),
    ) -> ProjectResponse:
        safe_project_path(wiki_root, project_id)
        if request.role not in {"viewer", "editor"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效项目角色")
        user = find_user(session, request.username)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        permission = find_project_permission(session, user.id, project_id)
        if permission is None:
            permission = ProjectPermission(user_id=user.id, project_id=project_id, role=request.role)
            session.add(permission)
        else:
            permission.role = request.role
        session.commit()
        return ProjectResponse(project_id=project_id, role=request.role)

    @app.get("/api/projects", response_model=list[ProjectResponse])
    def list_projects(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[ProjectResponse]:
        permissions = session.scalars(
            select(ProjectPermission).where(ProjectPermission.user_id == user.id).order_by(ProjectPermission.project_id)
        )
        return [ProjectResponse(project_id=permission.project_id, role=permission.role) for permission in permissions]

    @app.get("/api/projects/{project_id}/tree", response_model=list[TreeNode])
    def read_project_tree(
        project_id: str,
        path: str = Query(default="docs"),
        user: User = Depends(current_user),
        session: Session = Depends(get_session),
    ) -> list[TreeNode]:
        if find_project_permission(session, user.id, project_id) is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有项目权限")
        project_path = safe_project_path(wiki_root, project_id)
        directory = safe_document_directory(project_path, path)
        if not directory.is_dir():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目录不存在")

        return [
            TreeNode(
                title=entry.name,
                key=str(entry.relative_to(project_path)),
                is_leaf=entry.is_file(),
            )
            for entry in sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name))
            if entry.is_dir() or entry.suffix == ".md"
        ]

    return app


def safe_project_path(wiki_root: Path, project_id: str) -> Path:
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效项目标识")
    resolved_root = wiki_root.resolve()
    project_path = (resolved_root / project_id).resolve()
    if commonpath([str(resolved_root), str(project_path)]) != str(resolved_root):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效项目路径")
    return project_path


def safe_document_directory(project_path: Path, path: str) -> Path:
    docs_root = (project_path / "docs").resolve()
    directory = (project_path / path).resolve()
    if commonpath([str(docs_root), str(directory)]) != str(docs_root):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="无效文档路径")
    return directory


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
