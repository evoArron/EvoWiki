import json
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from os.path import commonpath
from pathlib import Path

import bcrypt
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import AuditLog, Project, ProjectPermission, Publication, User, create_session_factory, find_project, find_project_permission, find_user, session_dependency
from app.publishing import ChromaIndexer, GitRunner, Indexer, PublicationService, run_git

TOKEN_LIFETIME = timedelta(hours=8)
PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SERVICE_ROOT = Path(__file__).resolve().parent.parent
WIKI_ROOT = SERVICE_ROOT.parent / "enterprise-wiki-repo"
PROJECT_ROLES = {"viewer", "editor", "project_admin"}


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CreateMemberRequest(BaseModel):
    username: str
    display_name: str = Field(min_length=1, max_length=128)


class UpdateMemberRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)


class StatusRequest(BaseModel):
    is_active: bool


class SystemRoleRequest(BaseModel):
    role: str


class CreateProjectRequest(BaseModel):
    project_id: str
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str = ""
    owner_username: str | None = None


class UpdateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""


class OwnerRequest(BaseModel):
    owner_username: str


class GrantProjectPermissionRequest(BaseModel):
    username: str | None = None
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    username: str
    display_name: str
    role: str
    is_active: bool
    must_change_password: bool


class CreatedMemberResponse(CurrentUserResponse):
    temporary_password: str


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    description: str
    owner_username: str
    status: str
    role: str | None = None


class PermissionResponse(BaseModel):
    username: str
    display_name: str
    role: str


class AuditLogResponse(BaseModel):
    id: int
    actor_username: str
    action: str
    object_type: str
    object_id: str
    project_id: str | None
    before_summary: dict[str, object]
    after_summary: dict[str, object]
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    total: int


class TreeNode(BaseModel):
    title: str
    key: str
    is_leaf: bool


class DocumentResponse(BaseModel):
    path: str
    content: str
    git_commit: str | None = None


class DraftRequest(BaseModel):
    path: str = ""
    content: str


class PublishRequest(BaseModel):
    target_path: str
    overwrite: bool = False


class PublicationResponse(BaseModel):
    id: int
    project_id: str
    draft_path: str
    target_path: str | None
    status: str
    error: str | None
    git_commit: str | None


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
    git_runner: GitRunner = run_git,
    indexer: Indexer | None = None,
) -> FastAPI:
    database_path = database_path or SERVICE_ROOT / "evowiki.db"
    database_root = database_root or SERVICE_ROOT
    wiki_root = wiki_root or WIKI_ROOT
    jwt_secret = jwt_secret or required_environment("EVOWIKI_JWT_SECRET")
    initial_admin_username = initial_admin_username or required_environment("EVOWIKI_ADMIN_USERNAME")
    initial_admin_password = initial_admin_password or required_environment("EVOWIKI_ADMIN_PASSWORD")
    session_factory = create_session_factory(database_path, database_root)
    seed_admin(session_factory, initial_admin_username, initial_admin_password)
    publisher = PublicationService(wiki_root, git_runner, indexer or ChromaIndexer(database_root / "chroma"))

    app = FastAPI(title="EvoWiki MCP Server")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])

    def get_session() -> Session:
        yield from session_dependency(session_factory)

    def current_user(authorization: str | None = Header(default=None), session: Session = Depends(get_session)) -> User:
        if not authorization or not authorization.startswith("Bearer "):
            raise unauthorized()
        try:
            payload = jwt.decode(authorization.removeprefix("Bearer "), jwt_secret, algorithms=["HS256"])
            username, session_version = payload["sub"], payload["sv"]
        except (jwt.InvalidTokenError, KeyError):
            raise unauthorized() from None
        user = find_user(session, username)
        if user is None or not user.is_active or user.session_version != session_version:
            raise unauthorized()
        return user

    def ready_user(user: User = Depends(current_user)) -> User:
        if user.must_change_password:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要先修改临时密码")
        return user

    def admin_user(user: User = Depends(ready_user)) -> User:
        if user.role != "system_admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要系统管理员权限")
        return user

    def project_access(project_id: str, user: User, session: Session, require_write: bool = False) -> ProjectPermission:
        project = find_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        permission = find_project_permission(session, user.id, project_id)
        if user.role == "system_admin":
            permission = permission or ProjectPermission(user_id=user.id, project_id=project_id, role="project_admin")
        if permission is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有项目权限")
        if require_write and (project.status != "active" or permission.role == "viewer"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="项目不可写")
        return permission

    def project_manager(project_id: str, user: User, session: Session) -> Project:
        project = find_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        if project.status != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="归档项目不可管理")
        if user.role != "system_admin":
            permission = find_project_permission(session, user.id, project_id)
            if project.status != "active" or permission is None or permission.role != "project_admin":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要项目管理员权限")
        return project

    def audit(session: Session, actor: User, action: str, object_type: str, object_id: str, before: dict[str, object] | None = None, after: dict[str, object] | None = None, project_id: str | None = None) -> None:
        session.add(AuditLog(actor_id=actor.id, action=action, object_type=object_type, object_id=object_id, project_id=project_id, before_summary=json.dumps(before or {}, ensure_ascii=False), after_summary=json.dumps(after or {}, ensure_ascii=False)))

    def member_response(user: User) -> CurrentUserResponse:
        return CurrentUserResponse(username=user.username, display_name=user.display_name, role=user.role, is_active=user.is_active, must_change_password=user.must_change_password)

    def project_response(project: Project, session: Session, user: User | None = None) -> ProjectResponse:
        owner = session.get(User, project.owner_id)
        permission = find_project_permission(session, user.id, project.project_id) if user else None
        role = "project_admin" if user and user.role == "system_admin" else (permission.role if permission else None)
        return ProjectResponse(project_id=project.project_id, name=project.name, description=project.description, owner_username=owner.username if owner else "", status=project.status, role=role)

    def publication_response(publication: Publication) -> PublicationResponse:
        return PublicationResponse(id=publication.id, project_id=publication.project_id, draft_path=publication.draft_path, target_path=publication.target_path, status=publication.status, error=publication.error, git_commit=publication.git_commit)

    def publication_or_404(publication_id: int, project_id: str, session: Session) -> Publication:
        publication = session.get(Publication, publication_id)
        if publication is None or publication.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="草稿不存在")
        return publication

    @app.post("/api/auth/login", response_model=TokenResponse)
    def login(credentials: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
        user = find_user(session, credentials.username)
        try:
            password_matches = user is not None and bcrypt.checkpw(credentials.password.encode(), user.password_hash.encode())
        except ValueError:
            password_matches = False
        if user is None or not user.is_active or not password_matches:
            raise unauthorized()
        token = jwt.encode({"sub": user.username, "sv": user.session_version, "exp": datetime.now(UTC) + TOKEN_LIFETIME}, jwt_secret, algorithm="HS256")
        return TokenResponse(access_token=token)

    @app.get("/api/auth/me", response_model=CurrentUserResponse)
    def read_current_user(user: User = Depends(current_user)) -> CurrentUserResponse:
        return member_response(user)

    @app.post("/api/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
    def change_password(request: ChangePasswordRequest, user: User = Depends(current_user), session: Session = Depends(get_session)) -> None:
        try:
            valid = bcrypt.checkpw(request.current_password.encode(), user.password_hash.encode())
            password_hash = bcrypt.hashpw(request.new_password.encode(), bcrypt.gensalt()).decode()
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="当前密码错误或新密码过长")
        user.password_hash, user.must_change_password = password_hash, False
        user.session_version += 1
        session.commit()

    @app.get("/api/admin/members", response_model=list[CurrentUserResponse])
    def list_members(_: User = Depends(admin_user), session: Session = Depends(get_session)) -> list[CurrentUserResponse]:
        return [member_response(member) for member in session.scalars(select(User).order_by(User.username))]

    @app.post("/api/admin/members", status_code=status.HTTP_201_CREATED, response_model=CreatedMemberResponse)
    @app.post("/api/admin/users", status_code=status.HTTP_201_CREATED, response_model=CreatedMemberResponse)
    def create_member(request: CreateMemberRequest, session: Session = Depends(get_session), admin: User = Depends(admin_user)) -> CreatedMemberResponse:
        if find_user(session, request.username):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="登录名已存在")
        temporary_password = secrets.token_urlsafe(12)
        try:
            password_hash = bcrypt.hashpw(temporary_password.encode(), bcrypt.gensalt()).decode()
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="密码过长") from None
        member = User(username=request.username, display_name=request.display_name, password_hash=password_hash, role="member", must_change_password=True)
        session.add(member)
        session.flush()
        audit(session, admin, "member.created", "member", member.username, after={"display_name": member.display_name, "role": member.role})
        session.commit()
        return CreatedMemberResponse(**member_response(member).model_dump(), temporary_password=temporary_password)

    @app.patch("/api/admin/members/{username}", response_model=CurrentUserResponse)
    def update_member(username: str, request: UpdateMemberRequest, session: Session = Depends(get_session), admin: User = Depends(admin_user)) -> CurrentUserResponse:
        member = find_user(session, username)
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成员不存在")
        before = {"display_name": member.display_name}
        member.display_name = request.display_name
        audit(session, admin, "member.updated", "member", username, before, {"display_name": member.display_name})
        session.commit()
        return member_response(member)

    @app.post("/api/admin/members/{username}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
    def reset_password(username: str, request: PasswordRequest, session: Session = Depends(get_session), admin: User = Depends(admin_user)) -> None:
        member = find_user(session, username)
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成员不存在")
        try:
            member.password_hash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="密码过长") from None
        member.session_version += 1
        member.must_change_password = True
        audit(session, admin, "member.password_reset", "member", username)
        session.commit()

    @app.post("/api/admin/members/{username}/status", response_model=CurrentUserResponse)
    def set_member_status(username: str, request: StatusRequest, session: Session = Depends(get_session), admin: User = Depends(admin_user)) -> CurrentUserResponse:
        member = find_user(session, username)
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成员不存在")
        if not request.is_active and member.role == "system_admin" and session.scalar(select(func.count(User.id)).where(User.role == "system_admin", User.is_active)) == 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="必须保留一名启用的系统管理员")
        if not request.is_active and session.scalar(select(Project).where(Project.owner_id == member.id, Project.status == "active")):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先转移负责人或归档项目")
        before = {"is_active": member.is_active}
        member.is_active = request.is_active
        member.session_version += 1
        audit(session, admin, "member.status_changed", "member", username, before, {"is_active": member.is_active})
        session.commit()
        return member_response(member)

    @app.post("/api/admin/members/{username}/system-role", response_model=CurrentUserResponse)
    def set_system_role(username: str, request: SystemRoleRequest, session: Session = Depends(get_session), admin: User = Depends(admin_user)) -> CurrentUserResponse:
        member = find_user(session, username)
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成员不存在")
        if request.role not in {"member", "system_admin"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效系统角色")
        if member.role == "system_admin" and request.role != "system_admin" and session.scalar(select(func.count(User.id)).where(User.role == "system_admin", User.is_active)) == 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="必须保留一名启用的系统管理员")
        before = {"role": member.role}
        member.role = request.role
        audit(session, admin, "member.system_role_changed", "member", username, before, {"role": member.role})
        session.commit()
        return member_response(member)

    @app.get("/api/admin/projects", response_model=list[ProjectResponse])
    def list_admin_projects(_: User = Depends(admin_user), session: Session = Depends(get_session)) -> list[ProjectResponse]:
        return [project_response(project, session) for project in session.scalars(select(Project).order_by(Project.project_id))]

    @app.post("/api/admin/projects", status_code=status.HTTP_201_CREATED, response_model=ProjectResponse)
    def create_project(request: CreateProjectRequest, session: Session = Depends(get_session), admin: User = Depends(admin_user)) -> ProjectResponse:
        safe_project_path(wiki_root, request.project_id)
        if find_project(session, request.project_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="项目已存在")
        owner = find_user(session, request.owner_username) if request.owner_username else admin
        if owner is None or not owner.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="负责人必须是启用成员")
        project_path = safe_project_path(wiki_root, request.project_id)
        if project_path.exists():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="项目目录已存在")
        (project_path / "docs").mkdir(parents=True)
        project = Project(project_id=request.project_id, name=request.name or request.project_id, description=request.description, owner_id=owner.id)
        session.add(project)
        session.add(ProjectPermission(user_id=owner.id, project_id=project.project_id, role="project_admin"))
        audit(session, admin, "project.created", "project", project.project_id, after={"name": project.name, "owner_username": owner.username}, project_id=project.project_id)
        session.commit()
        return project_response(project, session, admin)

    @app.patch("/api/admin/projects/{project_id}", response_model=ProjectResponse)
    def update_project(project_id: str, request: UpdateProjectRequest, session: Session = Depends(get_session), user: User = Depends(ready_user)) -> ProjectResponse:
        project = project_manager(project_id, user, session)
        before = {"name": project.name, "description": project.description}
        project.name, project.description = request.name, request.description
        audit(session, user, "project.updated", "project", project_id, before, {"name": project.name, "description": project.description}, project_id)
        session.commit()
        return project_response(project, session, user)

    @app.post("/api/admin/projects/{project_id}/owner", response_model=ProjectResponse)
    def transfer_owner(project_id: str, request: OwnerRequest, session: Session = Depends(get_session), user: User = Depends(ready_user)) -> ProjectResponse:
        project = project_manager(project_id, user, session)
        owner = find_user(session, request.owner_username)
        if owner is None or not owner.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="负责人必须是启用成员")
        old_owner = session.get(User, project.owner_id)
        project.owner_id = owner.id
        permission = find_project_permission(session, owner.id, project_id)
        if permission is None:
            session.add(ProjectPermission(user_id=owner.id, project_id=project_id, role="project_admin"))
        else:
            permission.role = "project_admin"
        audit(session, user, "project.owner_transferred", "project", project_id, {"owner_username": old_owner.username if old_owner else ""}, {"owner_username": owner.username}, project_id)
        session.commit()
        return project_response(project, session, user)

    @app.post("/api/admin/projects/{project_id}/archive", response_model=ProjectResponse)
    def archive_project(project_id: str, session: Session = Depends(get_session), admin: User = Depends(admin_user)) -> ProjectResponse:
        project = find_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        if project.status != "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="项目已归档")
        project.status = "archived"
        audit(session, admin, "project.archived", "project", project_id, {"status": "active"}, {"status": "archived"}, project_id)
        session.commit()
        return project_response(project, session, admin)

    @app.post("/api/admin/projects/{project_id}/restore", response_model=ProjectResponse)
    def restore_project(project_id: str, session: Session = Depends(get_session), admin: User = Depends(admin_user)) -> ProjectResponse:
        project = find_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        if project.status != "archived":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="项目未归档")
        project.status = "active"
        audit(session, admin, "project.restored", "project", project_id, {"status": "archived"}, {"status": "active"}, project_id)
        session.commit()
        return project_response(project, session, admin)

    @app.get("/api/admin/projects/{project_id}/permissions", response_model=list[PermissionResponse])
    def list_permissions(project_id: str, session: Session = Depends(get_session), user: User = Depends(ready_user)) -> list[PermissionResponse]:
        project_manager(project_id, user, session)
        permissions = session.scalars(select(ProjectPermission).where(ProjectPermission.project_id == project_id).order_by(ProjectPermission.user_id))
        return [PermissionResponse(username=member.username, display_name=member.display_name, role=permission.role) for permission in permissions if (member := session.get(User, permission.user_id))]

    @app.put("/api/admin/projects/{project_id}/permissions/{username}", response_model=PermissionResponse)
    @app.post("/api/admin/projects/{project_id}/permissions", response_model=PermissionResponse)
    def grant_project_permission(project_id: str, username: str | None = None, request: GrantProjectPermissionRequest | None = None, session: Session = Depends(get_session), user: User = Depends(ready_user)) -> PermissionResponse:
        if request is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="缺少授权内容")
        username = username or request.username
        if not username:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="缺少成员登录名")
        project_manager(project_id, user, session)
        if request.role not in PROJECT_ROLES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效项目角色")
        project = find_project(session, project_id)
        member = find_user(session, username)
        if project and member and project.owner_id == member.id and request.role != "project_admin":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="负责人必须保留项目管理员权限")
        if member is None or not member.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成员不存在或已停用")
        permission = find_project_permission(session, member.id, project_id)
        before = {"role": permission.role} if permission else {}
        if permission is None:
            permission = ProjectPermission(user_id=member.id, project_id=project_id, role=request.role)
            session.add(permission)
        else:
            permission.role = request.role
        audit(session, user, "project.permission_changed", "project_permission", f"{project_id}:{username}", before, {"role": request.role}, project_id)
        session.commit()
        return PermissionResponse(username=member.username, display_name=member.display_name, role=request.role)

    @app.delete("/api/admin/projects/{project_id}/permissions/{username}", status_code=status.HTTP_204_NO_CONTENT)
    def revoke_project_permission(project_id: str, username: str, session: Session = Depends(get_session), user: User = Depends(ready_user)) -> None:
        project = project_manager(project_id, user, session)
        member = find_user(session, username)
        permission = find_project_permission(session, member.id, project_id) if member else None
        if permission is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="授权不存在")
        if project.owner_id == member.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先转移负责人")
        session.delete(permission)
        audit(session, user, "project.permission_revoked", "project_permission", f"{project_id}:{username}", {"role": permission.role}, project_id=project_id)
        session.commit()

    @app.get("/api/admin/members/{username}/projects", response_model=list[ProjectResponse])
    def list_member_projects(username: str, _: User = Depends(admin_user), session: Session = Depends(get_session)) -> list[ProjectResponse]:
        member = find_user(session, username)
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成员不存在")
        permissions = session.scalars(select(ProjectPermission).where(ProjectPermission.user_id == member.id))
        return [project_response(project, session, member) for permission in permissions if (project := find_project(session, permission.project_id))]

    @app.get("/api/admin/audit-logs", response_model=AuditLogPage)
    def list_audit_logs(page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100), action: str | None = None, _: User = Depends(admin_user), session: Session = Depends(get_session)) -> AuditLogPage:
        statement = select(AuditLog).order_by(AuditLog.id.desc())
        count_statement = select(func.count(AuditLog.id))
        if action:
            statement, count_statement = statement.where(AuditLog.action == action), count_statement.where(AuditLog.action == action)
        entries = session.scalars(statement.offset((page - 1) * page_size).limit(page_size))
        return AuditLogPage(items=[AuditLogResponse(id=entry.id, actor_username=(session.get(User, entry.actor_id).username if session.get(User, entry.actor_id) else ""), action=entry.action, object_type=entry.object_type, object_id=entry.object_id, project_id=entry.project_id, before_summary=json.loads(entry.before_summary), after_summary=json.loads(entry.after_summary), created_at=entry.created_at) for entry in entries], total=session.scalar(count_statement) or 0)

    @app.post("/api/projects/{project_id}/drafts", response_model=PublicationResponse, status_code=status.HTTP_201_CREATED)
    def create_draft(project_id: str, request: DraftRequest, user: User = Depends(ready_user), session: Session = Depends(get_session)) -> PublicationResponse:
        project_access(project_id, user, session, require_write=True)
        return publication_response(publisher.create_draft(session, project_id, request.path, request.content))

    @app.get("/api/projects/{project_id}/drafts", response_model=list[PublicationResponse])
    def list_drafts(project_id: str, user: User = Depends(ready_user), session: Session = Depends(get_session)) -> list[PublicationResponse]:
        project_access(project_id, user, session, require_write=True)
        return [publication_response(item) for item in session.scalars(select(Publication).where(Publication.project_id == project_id, Publication.status == "pending").order_by(Publication.id))]

    @app.get("/api/projects/{project_id}/drafts/{publication_id}", response_model=DocumentResponse)
    def read_draft(project_id: str, publication_id: int, user: User = Depends(ready_user), session: Session = Depends(get_session)) -> DocumentResponse:
        project_access(project_id, user, session, require_write=True)
        publication = publication_or_404(publication_id, project_id, session)
        path = publisher._safe_path(wiki_root, publication.draft_path)
        if publication.status != "pending" or not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="草稿不存在")
        return DocumentResponse(path=publication.draft_path, content=path.read_text(encoding="utf-8"))

    @app.put("/api/projects/{project_id}/drafts/{publication_id}", response_model=PublicationResponse)
    def update_draft(project_id: str, publication_id: int, request: DraftRequest, user: User = Depends(ready_user), session: Session = Depends(get_session)) -> PublicationResponse:
        project_access(project_id, user, session, require_write=True)
        publication = publication_or_404(publication_id, project_id, session)
        if publication.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="草稿不可修订")
        publisher.update_draft(publication, request.content)
        session.commit()
        return publication_response(publication)

    @app.delete("/api/projects/{project_id}/drafts/{publication_id}", status_code=status.HTTP_204_NO_CONTENT)
    def reject_draft(project_id: str, publication_id: int, user: User = Depends(ready_user), session: Session = Depends(get_session)) -> None:
        project_access(project_id, user, session, require_write=True)
        publication = publication_or_404(publication_id, project_id, session)
        if publication.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="草稿不可拒绝")
        publisher.reject_draft(publication)
        session.commit()

    @app.post("/api/projects/{project_id}/drafts/{publication_id}/publish", response_model=PublicationResponse)
    def publish_draft(project_id: str, publication_id: int, request: PublishRequest, user: User = Depends(ready_user), session: Session = Depends(get_session)) -> PublicationResponse:
        project_access(project_id, user, session, require_write=True)
        publication = publisher.publish(publication_or_404(publication_id, project_id, session), request.target_path, request.overwrite)
        session.commit()
        return publication_response(publication)

    @app.post("/api/projects/{project_id}/drafts/{publication_id}/retry", response_model=PublicationResponse)
    def retry_draft(project_id: str, publication_id: int, user: User = Depends(ready_user), session: Session = Depends(get_session)) -> PublicationResponse:
        project_access(project_id, user, session, require_write=True)
        publication = publisher.retry(publication_or_404(publication_id, project_id, session))
        session.commit()
        return publication_response(publication)

    @app.get("/api/projects", response_model=list[ProjectResponse])
    def list_projects(user: User = Depends(ready_user), session: Session = Depends(get_session)) -> list[ProjectResponse]:
        projects = session.scalars(select(Project).order_by(Project.project_id)) if user.role == "system_admin" else [find_project(session, permission.project_id) for permission in session.scalars(select(ProjectPermission).where(ProjectPermission.user_id == user.id))]
        return [project_response(project, session, user) for project in projects if project is not None]

    @app.get("/api/projects/{project_id}/tree", response_model=list[TreeNode])
    def read_project_tree(project_id: str, path: str = Query(default="docs"), user: User = Depends(ready_user), session: Session = Depends(get_session)) -> list[TreeNode]:
        project_access(project_id, user, session)
        project_path = safe_project_path(wiki_root, project_id)
        directory = safe_document_directory(project_path, path)
        if not directory.is_dir():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目录不存在")
        return [TreeNode(title=entry.name, key=str(entry.relative_to(project_path)), is_leaf=entry.is_file()) for entry in sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name)) if entry.is_dir() or entry.suffix == ".md"]

    @app.get("/api/projects/{project_id}/documents", response_model=DocumentResponse)
    def read_document(project_id: str, path: str, user: User = Depends(ready_user), session: Session = Depends(get_session)) -> DocumentResponse:
        project_access(project_id, user, session)
        project_path = safe_project_path(wiki_root, project_id)
        document_path = safe_markdown_document_path(project_path, path)
        if not document_path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
        relative_path = str(document_path.relative_to(wiki_root))
        publication = session.scalar(select(Publication).where(Publication.project_id == project_id, Publication.target_path == relative_path, Publication.status == "indexed"))
        if publication is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档尚未发布")
        return DocumentResponse(path=str(document_path.relative_to(project_path)), content=document_path.read_text(encoding="utf-8"), git_commit=publication.git_commit)

    mcp = FastMCP("EvoWiki")

    def mcp_user(access_token: str, session: Session) -> User:
        try:
            payload = jwt.decode(access_token.removeprefix("Bearer "), jwt_secret, algorithms=["HS256"])
            user = find_user(session, payload["sub"])
        except (jwt.InvalidTokenError, KeyError):
            raise ValueError("认证失败") from None
        if user is None or not user.is_active or user.session_version != payload["sv"] or user.must_change_password:
            raise ValueError("认证失败")
        return user

    @mcp.tool(description="向有编辑权限的项目提交待核对 Markdown 草稿。此工具不能发布、推送或索引内容。")
    def upload_draft(access_token: str, project_id: str, path: str, content: str) -> dict[str, object]:
        with session_factory() as session:
            user = mcp_user(access_token, session)
            project_access(project_id, user, session, require_write=True)
            return publication_response(publisher.create_draft(session, project_id, path, content)).model_dump()

    @mcp.tool(description="读取调用者有权访问且已推送、已索引的正式 Markdown 原文。")
    def read_published_document(access_token: str, project_id: str, path: str) -> dict[str, str]:
        with session_factory() as session:
            user = mcp_user(access_token, session)
            project_access(project_id, user, session)
            project_path = safe_project_path(wiki_root, project_id)
            document_path = safe_markdown_document_path(project_path, path)
            publication = session.scalar(select(Publication).where(Publication.project_id == project_id, Publication.target_path == str(document_path.relative_to(wiki_root)), Publication.status == "indexed"))
            if publication is None or not document_path.is_file():
                raise ValueError("文档不存在或尚未发布")
            return {"path": publication.target_path or "", "content": document_path.read_text(encoding="utf-8"), "git_commit": publication.git_commit or ""}

    @mcp.tool(description="检索调用者有权访问项目中的已索引原文块，并返回标题、路径和 Git commit 来源。")
    def search_published_documents(access_token: str, query: str, project_ids: list[str] | None = None) -> list[dict[str, str]]:
        if not isinstance(publisher.indexer, ChromaIndexer):
            raise ValueError("原文 RAG 索引器不可用")
        with session_factory() as session:
            user = mcp_user(access_token, session)
            allowed = [project.project_id for project in session.scalars(select(Project)) if (user.role == "system_admin" or find_project_permission(session, user.id, project.project_id))]
            requested = project_ids or allowed
            if any(project_id not in allowed for project_id in requested):
                raise ValueError("没有项目权限")
            return publisher.indexer.search(requested, query)

    app.mount("/mcp", mcp.streamable_http_app())
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
    resolved_project_path = project_path.resolve()
    docs_root = (project_path / "docs").resolve()
    if commonpath([str(resolved_project_path), str(docs_root)]) != str(resolved_project_path):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="无效文档根目录")
    directory = (project_path / path).resolve()
    if commonpath([str(docs_root), str(directory)]) != str(docs_root):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="无效文档路径")
    return directory


def safe_markdown_document_path(project_path: Path, path: str) -> Path:
    document_path = safe_document_directory(project_path, path)
    if document_path.suffix != ".md":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="仅支持 Markdown 文档")
    return document_path


def seed_admin(factory: sessionmaker[Session], username: str, password: str) -> None:
    with factory.begin() as session:
        if find_user(session, username) is None:
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            session.add(User(username=username, display_name=username, password_hash=password_hash, role="system_admin", must_change_password=False))


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:create_app", factory=True, host=os.getenv("EVOWIKI_HOST", "127.0.0.1"), port=int(os.getenv("EVOWIKI_PORT", "8000")))


def unauthorized() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证失败", headers={"WWW-Authenticate": "Bearer"})
