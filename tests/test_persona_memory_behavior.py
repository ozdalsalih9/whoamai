from datetime import datetime

import app.main as main


class CapturingMemory:
    def __init__(self, global_plan_context: str = "") -> None:
        self.global_plan_context = global_plan_context
        self.added: list[dict[str, object]] = []
        self.deleted_at: list[float] = []

    def add_chat_memory(self, text: str, timestamp: str, user_hash: str, **metadata: object) -> str:
        self.added.append(
            {
                "text": text,
                "timestamp": timestamp,
                "user_hash": user_hash,
                **metadata,
            }
        )
        return "mem_test"

    def delete_expired_memories(self, now_ts: float) -> int:
        self.deleted_at.append(now_ts)
        return 0

    def retrieve_active_global_plans(self, top_k: int = 3, now_ts: float | None = None) -> str:
        return self.global_plan_context


def test_deterministic_short_replies(monkeypatch) -> None:
    monkeypatch.setattr(main, "memory", CapturingMemory())

    assert main.deterministic_reply("Naber kanka?") == main.STATUS_REPLY
    assert main.deterministic_reply("Naber React tarafinda durum ne?") is None
    assert main.deterministic_reply("Planin var mi bir seyler yapalim mi?") == main.NO_PLAN_REPLY
    assert main.deterministic_reply("Cok iyi olmus.") in {"sa\u011fol", "eyw"}


def test_deterministic_plan_query_uses_active_global_plan(monkeypatch) -> None:
    context = "[GLOBAL_PLAN: WhatsApp Memory]\nMustafa sunu hatirlamami istedi: 30 dakika sonra AVM ye gidecegim."
    monkeypatch.setattr(main, "memory", CapturingMemory(global_plan_context=context))

    reply = main.deterministic_reply("Yarim saat sonra ne yapacaksin?")

    assert reply == "AVM ye gidecegim."


def test_owner_explicit_memory_is_global_and_temporary(monkeypatch) -> None:
    fake_memory = CapturingMemory()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=main.ISTANBUL_TZ)
    monkeypatch.setattr(main, "memory", fake_memory)
    monkeypatch.setattr(main.settings, "owner_wa_ids", "owner-wa")

    reply = main.store_explicit_owner_memory("owner-wa", "30 dakika sonra AVM ye gidecegim bunu unutma", now=now)

    assert reply == main.GLOBAL_MEMORY_REPLY
    assert len(fake_memory.added) == 1
    stored = fake_memory.added[0]
    assert stored["visibility"] == "global"
    assert stored["memory_kind"] == "plan"
    assert stored["owner_hash"] == main.user_hash("owner-wa")
    assert stored["expires_at_ts"] == now.timestamp() + 30 * 60
    assert "AVM ye gidecegim" in str(stored["text"])


def test_non_owner_explicit_memory_is_not_global(monkeypatch) -> None:
    fake_memory = CapturingMemory()
    monkeypatch.setattr(main, "memory", fake_memory)
    monkeypatch.setattr(main.settings, "owner_wa_ids", "owner-wa")

    reply = main.store_explicit_owner_memory("other-wa", "30 dakika sonra AVM ye gidecegim bunu unutma")

    assert reply is None
    assert fake_memory.added == []
