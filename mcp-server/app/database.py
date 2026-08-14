from collections.abc import Generator
from os.path import commonpath
from pathlib import Path

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="admin")


class ProjectPermission(Base):
    __tablename__ = "project_permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    file_path: Mapped[str] = mapped_column(String(512))
    anchor_text: Mapped[str] = mapped_column(String)
    json_thread: Mapped[str] = mapped_column(String, default="[]")
    status: Mapped[str] = mapped_column(String(16), default="open")


def create_session_factory(database_path: Path, database_root: Path) -> sessionmaker[Session]:
    resolved_path = database_path.resolve()
    resolved_root = database_root.resolve()
    if resolved_path.name != "evowiki.db" or commonpath([str(resolved_path), str(resolved_root)]) != str(resolved_root):
        raise ValueError("数据库文件必须位于服务目录")

    engine = create_engine(f"sqlite:///{resolved_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def find_user(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def session_dependency(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    with factory() as session:
        yield session
