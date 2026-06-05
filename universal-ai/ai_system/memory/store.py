from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from ai_system.core.config import Settings


@dataclass
class MemoryStore:
    settings: Settings

    def __post_init__(self) -> None:
        self.settings.memory_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(self.settings.memory_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=self.settings.memory_collection,
            embedding_function=DefaultEmbeddingFunction(),
            metadata={"description": "AI_System long-term memory"},
        )

    def remember(self, text: str, kind: str = "note", source: str = "user") -> str:
        memory_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.collection.add(
            ids=[memory_id],
            documents=[text],
            metadatas=[{"kind": kind, "source": source, "created_at": now}],
        )
        return memory_id

    def recall(self, query: str, limit: int = 5) -> list[str]:
        if not query.strip():
            return []
        count = self.collection.count()
        if count == 0:
            return []
        result = self.collection.query(query_texts=[query], n_results=min(limit, count))
        documents = result.get("documents", [[]])
        return [doc for doc in documents[0] if doc]

    def count(self) -> int:
        return self.collection.count()
