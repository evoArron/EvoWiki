import subprocess
from os.path import commonpath
from pathlib import Path
from threading import Lock
from typing import Callable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Publication

GitRunner = Callable[[list[str], Path], str]
Indexer = Callable[[str, str, str, str], None]


class PublicationService:
    # ponytail: process-wide lock; split by repository only if multiple repositories are introduced.
    lock = Lock()

    def __init__(self, wiki_root: Path, git_runner: GitRunner, indexer: Indexer):
        self.wiki_root = wiki_root.resolve()
        self.git_runner = git_runner
        self.indexer = indexer

    def draft_path(self, project_id: str, path: str) -> Path:
        return self._safe_path(self.wiki_root / project_id / ".drafts", path)

    def document_path(self, project_id: str, path: str) -> Path:
        return self._safe_path(self.wiki_root / project_id / "docs", path)

    def create_draft(self, session: Session, project_id: str, path: str, content: str) -> Publication:
        draft_path = self.draft_path(project_id, path)
        if draft_path.suffix != ".md":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="仅支持 Markdown 文档")
        if session.scalar(select(Publication).where(Publication.draft_path == str(draft_path.relative_to(self.wiki_root)))):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="草稿已存在")
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(content, encoding="utf-8")
        publication = Publication(project_id=project_id, draft_path=str(draft_path.relative_to(self.wiki_root)))
        session.add(publication)
        session.commit()
        return publication

    def update_draft(self, publication: Publication, content: str) -> None:
        path = self._safe_path(self.wiki_root, publication.draft_path)
        path.write_text(content, encoding="utf-8")

    def reject_draft(self, publication: Publication) -> None:
        path = self._safe_path(self.wiki_root, publication.draft_path)
        if path.exists():
            path.unlink()
        publication.status = "rejected"

    def publish(self, publication: Publication, target_path: str, overwrite: bool) -> Publication:
        with self.lock:
            if publication.status != "pending":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="草稿不可发布")
            draft_path = self._safe_path(self.wiki_root, publication.draft_path)
            document_path = self.document_path(publication.project_id, target_path)
            if document_path.suffix != ".md":
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="仅支持 Markdown 文档")
            if document_path.exists() and not overwrite:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="目标文档已存在，请明确确认覆盖")
            document_path.parent.mkdir(parents=True, exist_ok=True)
            document_path.write_text(draft_path.read_text(encoding="utf-8"), encoding="utf-8")
            relative_target = str(document_path.relative_to(self.wiki_root))
            try:
                self.git_runner(["add", "--", relative_target], self.wiki_root)
                self.git_runner(["commit", "-m", f"docs({publication.project_id}): publish {document_path.name}", "--", relative_target], self.wiki_root)
                publication.git_commit = self.git_runner(["rev-parse", "HEAD"], self.wiki_root).strip()
                publication.target_path = relative_target
                publication.status = "committed"
                self.git_runner(["push"], self.wiki_root)
                publication.status = "pushed"
                self.indexer(publication.project_id, relative_target, document_path.read_text(encoding="utf-8"), publication.git_commit)
                publication.status = "indexed"
                publication.error = None
            except RuntimeError as error:
                publication.status = "failed"
                publication.error = str(error)
            return publication

    def retry(self, publication: Publication) -> Publication:
        if publication.status != "failed" or not publication.target_path or not publication.git_commit:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="发布不可重试")
        with self.lock:
            try:
                self.git_runner(["push"], self.wiki_root)
                publication.status = "pushed"
                document_path = self._safe_path(self.wiki_root, publication.target_path)
                self.indexer(publication.project_id, publication.target_path, document_path.read_text(encoding="utf-8"), publication.git_commit)
                publication.status = "indexed"
                publication.error = None
            except RuntimeError as error:
                publication.error = str(error)
            return publication

    @staticmethod
    def _safe_path(root: Path, path: str) -> Path:
        resolved_root = root.resolve()
        candidate = (resolved_root / path).resolve()
        if commonpath([str(resolved_root), str(candidate)]) != str(resolved_root):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="非法文件路径")
        return candidate


def run_git(arguments: list[str], repository: Path) -> str:
    completed = subprocess.run(["git", *arguments], cwd=repository, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Git 操作失败")
    return completed.stdout


class ChromaIndexer:
    def __init__(self, index_root: Path):
        import chromadb

        self.collection = chromadb.PersistentClient(path=str(index_root)).get_or_create_collection("published_documents")

    def __call__(self, project_id: str, path: str, content: str, git_commit: str) -> None:
        chunks = chunk_markdown(content)
        self.collection.delete(where={"$and": [{"project_id": project_id}, {"path": path}]})
        self.collection.upsert(
            ids=[f"{project_id}:{path}:{git_commit}:{index}" for index, _ in enumerate(chunks)],
            documents=[chunk for _, chunk in chunks],
            metadatas=[{"project_id": project_id, "path": path, "git_commit": git_commit, "heading": heading} for heading, _ in chunks],
        )

    def search(self, project_ids: list[str], query: str, limit: int = 10) -> list[dict[str, str]]:
        if not project_ids:
            return []
        result = self.collection.query(query_texts=[query], n_results=limit, where={"project_id": {"$in": project_ids}}, include=["documents", "metadatas"])
        documents, metadatas = result["documents"][0], result["metadatas"][0]
        return [{"chunk": document, "heading": metadata["heading"], "path": metadata["path"], "git_commit": metadata["git_commit"], "project_id": metadata["project_id"]} for document, metadata in zip(documents, metadatas)]


def chunk_markdown(content: str) -> list[tuple[str, str]]:
    heading = ""
    chunks: list[tuple[str, str]] = []
    lines: list[str] = []
    in_code_fence = False
    for line in content.splitlines():
        if line.startswith("```"):
            in_code_fence = not in_code_fence
        if not in_code_fence and line.startswith("#") and line.lstrip("#").startswith(" "):
            if lines:
                chunks.append((heading, "\n".join(lines).strip()))
            heading, lines = line.lstrip("#").strip(), [line]
        else:
            lines.append(line)
    if lines:
        chunks.append((heading, "\n".join(lines).strip()))
    return [(title, text) for title, text in chunks if text]
