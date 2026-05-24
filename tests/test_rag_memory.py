import pytest

pytest.importorskip("chromadb")

from app.rag import ChromaMemory


class StaticEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


def test_chat_memory_retrieval_is_scoped_by_user_hash(tmp_path) -> None:
    memory = ChromaMemory(
        persist_path=str(tmp_path / "chroma"),
        collection_name="test_memory",
        embedder=StaticEmbedder(),
        max_context_chars=1000,
        min_score=0.0,
    )

    memory.add_chat_memory("Kullanici React tercih ediyor.", "2026-01-01T00:00:00", user_hash="user_a")
    memory.add_chat_memory("Kullanici Vue tercih ediyor.", "2026-01-01T00:00:01", user_hash="user_b")

    result = memory.retrieve_chat_memory("hangi framework", user_hash="user_a", top_k=5)

    assert "React tercih ediyor" in result
    assert "Vue tercih ediyor" not in result


def test_persona_reset_preserves_chat_memory(tmp_path) -> None:
    markdown_path = tmp_path / "mustafa_persona.md"
    markdown_path.write_text("# Persona\n\n## Spor\n- Galatasaray.", encoding="utf-8")
    memory = ChromaMemory(
        persist_path=str(tmp_path / "chroma"),
        collection_name="test_persona",
        embedder=StaticEmbedder(),
        max_context_chars=1000,
        min_score=0.0,
    )

    memory.add_chat_memory("Kullanici yarin Istanbul'a gidiyor.", "2026-01-01T00:00:00", user_hash="user_a")
    count = memory.reset_from_markdown(str(markdown_path))

    assert count == 1
    assert memory.count_by_scope("persona") == 1
    assert "Istanbul'a gidiyor" in memory.retrieve_chat_memory("yarin", user_hash="user_a", top_k=5)
