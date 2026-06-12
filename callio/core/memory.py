from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from callio.config.settings import Settings, get_settings
from callio.core.database import Database

try:
    import chromadb
except Exception:  # pragma: no cover - optional dependency
    chromadb = None


class MemoryHub:
    def __init__(self, database: Database, settings: Settings | None = None) -> None:
        self.database = database
        self.settings = settings or get_settings()
        self._working_memory: dict[str, deque[str]] = defaultdict(
            lambda: deque(maxlen=self.settings.session_token_limit)
        )
        self._semantic_fallback: list[dict[str, str]] = []
        self._semantic_collection = self._build_semantic_collection()

    def _build_semantic_collection(self) -> Any | None:
        if chromadb is None:
            return None
        client = chromadb.Client()
        return client.get_or_create_collection(name="callio_semantic_memory")

    def append_session_token(self, session_id: str, token: str) -> None:
        self._working_memory[session_id].append(token)

    def get_session_tokens(self, session_id: str) -> list[str]:
        return list(self._working_memory[session_id])

    def store_episode(self, session_id: str, title: str, transcript: str, summary: str) -> None:
        self.database.create_session(session_id, title, transcript, summary)
        self.add_semantic_memory(
            document_id=session_id,
            content=summary or transcript,
            metadata={"kind": "session", "title": title},
        )

    def add_semantic_memory(self, document_id: str, content: str, metadata: dict[str, str] | None = None) -> None:
        payload = metadata or {}
        if self._semantic_collection is not None:
            self._semantic_collection.upsert(
                ids=[document_id],
                documents=[content],
                metadatas=[payload],
            )
            return
        self._semantic_fallback = [entry for entry in self._semantic_fallback if entry["id"] != document_id]
        self._semantic_fallback.append({"id": document_id, "content": content, "metadata": str(payload)})

    def search_semantic_memory(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        if self._semantic_collection is not None:
            result = self._semantic_collection.query(query_texts=[query], n_results=limit)
            documents = result.get("documents", [[]])[0]
            ids = result.get("ids", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            return [
                {"id": doc_id, "content": doc, "metadata": str(meta)}
                for doc_id, doc, meta in zip(ids, documents, metadatas)
            ]
        query_terms = {term for term in query.lower().split() if term}
        ranked = []
        for entry in self._semantic_fallback:
            content_terms = set(entry["content"].lower().split())
            ranked.append((len(query_terms & content_terms), entry))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in ranked[:limit] if _ > 0 or not query_terms]
