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


def test_global_plan_memory_is_retrieved_until_expiry(tmp_path) -> None:
    memory = ChromaMemory(
        persist_path=str(tmp_path / "chroma"),
        collection_name="test_global_plan",
        embedder=StaticEmbedder(),
        max_context_chars=1000,
        min_score=0.0,
    )

    memory.add_chat_memory(
        "Mustafa sunu hatirlamami istedi: 30 dakika sonra AVM ye gidecegim.",
        "2026-01-01T12:00:00",
        user_hash="owner_a",
        memory_kind="plan",
        visibility="global",
        created_at_ts=1000.0,
        event_at_ts=2800.0,
        expires_at_ts=2800.0,
        owner_hash="owner_a",
    )

    active = memory.retrieve_active_global_plans(top_k=3, now_ts=2000.0)
    expired = memory.retrieve_active_global_plans(top_k=3, now_ts=2800.0)

    assert "AVM ye gidecegim" in active
    assert expired == ""


def test_delete_expired_memories_removes_only_expired_chat_memory(tmp_path) -> None:
    memory = ChromaMemory(
        persist_path=str(tmp_path / "chroma"),
        collection_name="test_expiry_cleanup",
        embedder=StaticEmbedder(),
        max_context_chars=1000,
        min_score=0.0,
    )

    memory.add_chat_memory(
        "Mustafa sunu hatirlamami istedi: eski plan.",
        "2026-01-01T12:00:00",
        user_hash="owner_a",
        memory_kind="plan",
        visibility="global",
        expires_at_ts=1000.0,
        owner_hash="owner_a",
    )
    memory.add_chat_memory(
        "Mustafa sunu hatirlamami istedi: aktif plan.",
        "2026-01-01T12:01:00",
        user_hash="owner_a",
        memory_kind="plan",
        visibility="global",
        expires_at_ts=3000.0,
        owner_hash="owner_a",
    )

    deleted = memory.delete_expired_memories(now_ts=2000.0)
    active = memory.retrieve_active_global_plans(top_k=3, now_ts=2000.0)

    assert deleted == 1
    assert "aktif plan" in active
    assert "eski plan" not in active
