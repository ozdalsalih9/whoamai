import hashlib
import re
from pathlib import Path
from typing import Any

import httpx


def chunk_markdown(markdown: str, chunk_size: int = 700, overlap: int = 120) -> list[dict[str, str]]:
    sections = re.split(r"(?m)^##\s+", markdown)
    chunks: list[dict[str, str]] = []

    for raw_section in sections:
        section = raw_section.strip()
        if not section:
            continue

        lines = section.splitlines()
        title = lines[0].strip("# ").strip() if lines else "Genel"
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else section
        text = f"## {title}\n{body}".strip()

        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({"title": title, "text": chunk_text})
            if end == len(text):
                break
            start = max(0, end - overlap)

    return chunks


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
            )
            response.raise_for_status()
            data = response.json()

        embeddings = data.get("embeddings")
        if embeddings:
            return embeddings

        embedding = data.get("embedding")
        if embedding:
            return [embedding]

        raise RuntimeError("Ollama embedding response did not include embeddings.")


class ChromaMemory:
    def __init__(
        self,
        persist_path: str,
        collection_name: str,
        embedder: OllamaEmbedder,
        max_context_chars: int = 1200,
        min_score: float = 0.25,
    ) -> None:
        import chromadb

        self.client = chromadb.PersistentClient(path=persist_path)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.embedder = embedder
        self.max_context_chars = max_context_chars
        self.min_score = min_score

    def count(self) -> int:
        return self.collection.count()

    def count_by_scope(self, scope: str) -> int:
        result = self.collection.get(where={"scope": scope}, include=[])
        return len(result.get("ids", []))

    def reset_from_markdown(self, markdown_path: str) -> int:
        path = Path(markdown_path)
        markdown = path.read_text(encoding="utf-8")
        chunks = chunk_markdown(markdown)

        existing = self.collection.get(include=["metadatas"])
        existing_ids = [
            item_id
            for item_id, metadata in zip(existing.get("ids", []), existing.get("metadatas", []))
            if self._is_persona_metadata(metadata, path.name)
        ]
        if existing_ids:
            self.collection.delete(ids=existing_ids)

        if not chunks:
            return 0

        documents = [chunk["text"] for chunk in chunks]
        embeddings = self.embedder.embed(documents)
        ids = [self._stable_id(path, chunk["title"], chunk["text"]) for chunk in chunks]
        metadatas = [{"scope": "persona", "source": path.name, "title": chunk["title"]} for chunk in chunks]

        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return len(chunks)

    def add_memory(self, text: str, metadata: dict[str, Any]) -> str:
        cleaned = " ".join(text.split())
        if not cleaned:
            raise ValueError("Memory text cannot be empty.")

        memory_id = self._memory_id(cleaned, str(metadata.get("timestamp", "")))
        embedding = self.embedder.embed([cleaned])[0]
        normalized_metadata = {
            key: value
            for key, value in metadata.items()
            if isinstance(value, str | int | float | bool)
        }

        self.collection.upsert(
            ids=[memory_id],
            documents=[cleaned],
            embeddings=[embedding],
            metadatas=[normalized_metadata],
        )
        return memory_id

    def add_chat_memory(self, text: str, timestamp: str, user_hash: str) -> str:
        return self.add_memory(
            text,
            {
                "scope": "chat_memory",
                "source": "whatsapp_chat",
                "timestamp": timestamp,
                "title": "WhatsApp Memory",
                "user_hash": user_hash,
            },
        )

    def retrieve_persona(self, query: str, top_k: int = 3) -> str:
        return self._retrieve(query, top_k=top_k, where={"scope": "persona"}, label="PERSONA")

    def retrieve_chat_memory(self, query: str, user_hash: str, top_k: int = 3) -> str:
        return self._retrieve(
            query,
            top_k=top_k,
            where={"$and": [{"scope": "chat_memory"}, {"user_hash": user_hash}]},
            label="CHAT_MEMORY",
        )

    def retrieve(self, query: str, top_k: int = 3) -> str:
        return self.retrieve_persona(query, top_k=top_k)

    def _retrieve(self, query: str, top_k: int, where: dict[str, Any], label: str) -> str:
        if self.count() == 0:
            return ""

        query_embedding = self.embedder.embed([query])[0]
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "distances", "metadatas"],
        )

        documents = result.get("documents", [[]])[0]
        distances = result.get("distances", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]

        selected: list[str] = []
        total_chars = 0
        for document, distance, metadata in zip(documents, distances, metadatas):
            score = max(0.0, 1.0 - float(distance))
            if score < self.min_score:
                continue

            title = metadata.get("title", "Baglam") if isinstance(metadata, dict) else "Baglam"
            entry = f"[{label}: {title} | skor={score:.2f}]\n{document.strip()}"
            if total_chars + len(entry) > self.max_context_chars:
                break
            selected.append(entry)
            total_chars += len(entry)

        return "\n\n".join(selected)

    @staticmethod
    def _stable_id(path: Path, title: str, text: str) -> str:
        digest = hashlib.sha256(f"{path.name}:{title}:{text}".encode("utf-8")).hexdigest()
        return digest[:32]

    @staticmethod
    def _memory_id(text: str, timestamp: str) -> str:
        digest = hashlib.sha256(f"whatsapp_chat:{timestamp}:{text}".encode("utf-8")).hexdigest()
        return f"mem_{digest[:28]}"

    @staticmethod
    def _is_persona_metadata(metadata: Any, source_name: str) -> bool:
        if not isinstance(metadata, dict):
            return False
        if metadata.get("scope") == "persona":
            return True
        return metadata.get("source") == source_name and metadata.get("source") != "whatsapp_chat"
