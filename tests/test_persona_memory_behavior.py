from datetime import datetime

import app.main as main


class CapturingMemory:
    def __init__(
        self,
        global_plan_context: str = "",
        global_memory_context: str = "",
        response_rules: list[dict[str, str]] | None = None,
    ) -> None:
        self.global_plan_context = global_plan_context
        self.global_memory_context = global_memory_context
        self.response_rules = response_rules or []
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

    def retrieve_global_memory(self, query: str, top_k: int = 3, now_ts: float | None = None) -> str:
        return self.global_memory_context

    def get_global_response_rules(self, now_ts: float | None = None) -> list[dict[str, str]]:
        return self.response_rules


def test_deterministic_short_replies(monkeypatch) -> None:
    monkeypatch.setattr(main, "memory", CapturingMemory())

    assert main.deterministic_reply("Naber kanka?") == main.STATUS_REPLY
    assert main.deterministic_reply("Naber React tarafinda durum ne?") is None
    assert main.deterministic_reply("30dk sonra AVM ye gidecegim, unutma") is None
    assert main.deterministic_reply("Planin var mi bir seyler yapalim mi?") == main.NO_PLAN_REPLY
    assert main.deterministic_reply("Cok iyi olmus.") in {"sa\u011fol", "eyw"}


def test_self_intro_uses_known_persona_facts() -> None:
    reply = main.deterministic_reply("Bana biraz kendinden bahset")

    assert "Mustafa Salih" in reply
    assert "22 yasindayim" in reply
    assert "Istanbul" in reply
    assert "D\u00fczce" in reply
    assert "AI" in reply


def test_learned_response_rule_overrides_default(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "memory",
        CapturingMemory(
            response_rules=[
                {
                    "question_key": main.response_rule_key("Naber?"),
                    "question_text": "Naber?",
                    "answer_text": "iyi kanka yuvarlanip gidioz",
                }
            ]
        ),
    )

    assert main.deterministic_reply("Naber?") == "iyi kanka yuvarlanip gidioz"


def test_profile_questions_use_persona_knowledge() -> None:
    assert main.deterministic_reply("Kac yasindasin?") == "22 yasindayim."
    assert main.deterministic_reply("Boyun kac?") == "Boyum 178."
    assert "D\u00fczce" in main.deterministic_reply("Hangi universite?")


def test_deterministic_plan_query_uses_active_global_plan(monkeypatch) -> None:
    context = "[GLOBAL_PLAN: WhatsApp Memory]\nMustafa sunu hatirlamami istedi: 30 dakika sonra AVM ye gidecegim."
    monkeypatch.setattr(main, "memory", CapturingMemory(global_plan_context=context))

    reply = main.deterministic_reply("Yarim saat sonra ne yapacaksin?")

    assert reply == "AVM ye gidecegim."


def test_deterministic_plan_query_prefers_matching_weekday(monkeypatch) -> None:
    context = (
        "[GLOBAL_PLAN: WhatsApp Memory]\n"
        "Mustafa sunu hatirlamami istedi: 30 dakika sonra AVM ye gidecegim.\n\n"
        "[GLOBAL_PLAN: WhatsApp Memory]\n"
        "Mustafa sunu hatirlamami istedi: Cuma gunu Suheyla'ya kavusacagim."
    )
    monkeypatch.setattr(main, "memory", CapturingMemory(global_plan_context=context))

    reply = main.deterministic_reply("Cuma gunu ne yapacaksin?")

    assert "Suheyla'ya kavusacagim" in reply
    assert "AVM" not in reply


def test_weekday_query_can_use_older_global_fact_memory(monkeypatch) -> None:
    plan_context = "[GLOBAL_PLAN: WhatsApp Memory]\nMustafa sunu hatirlamami istedi: 30 dakika sonra AVM ye gidecegim."
    fact_context = "[GLOBAL_MEMORY: WhatsApp Memory]\nMustafa sunu hatirlamami istedi: Cuma gunu Suheyla'ya kavusacagim."
    monkeypatch.setattr(
        main,
        "memory",
        CapturingMemory(global_plan_context=plan_context, global_memory_context=fact_context),
    )

    reply = main.deterministic_reply("Cuma gunu ne yapacaksin?")

    assert "Suheyla'ya kavusacagim" in reply
    assert "AVM" not in reply


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


def test_weekday_memory_is_stored_as_expiring_plan(monkeypatch) -> None:
    fake_memory = CapturingMemory()
    now = datetime(2026, 5, 25, 12, 0, tzinfo=main.ISTANBUL_TZ)
    friday_end = datetime(2026, 5, 29, 23, 59, 59, tzinfo=main.ISTANBUL_TZ)
    monkeypatch.setattr(main, "memory", fake_memory)
    monkeypatch.setattr(main.settings, "owner_wa_ids", "owner-wa")

    reply = main.store_explicit_owner_memory(
        "owner-wa",
        "Cuma gunu Suheyla'ya kavusacagim unutma",
        now=now,
    )

    assert reply == main.GLOBAL_MEMORY_REPLY
    stored = fake_memory.added[0]
    assert stored["memory_kind"] == "plan"
    assert stored["expires_at_ts"] == friday_end.timestamp()
    assert "Suheyla'ya kavusacagim" in str(stored["text"])


def test_response_rule_memory_is_stored_with_question_metadata(monkeypatch) -> None:
    fake_memory = CapturingMemory()
    now = datetime(2026, 5, 25, 12, 0, tzinfo=main.ISTANBUL_TZ)
    monkeypatch.setattr(main, "memory", fake_memory)
    monkeypatch.setattr(main.settings, "owner_wa_ids", "owner-wa")

    reply = main.store_explicit_owner_memory(
        "owner-wa",
        'Ben "Naber?" sorusuna "iyi kanka yuvarlanip gidioz" diye cevap veririm, unutma',
        now=now,
    )

    assert reply == main.GLOBAL_MEMORY_REPLY
    stored = fake_memory.added[0]
    assert stored["memory_kind"] == "response_rule"
    assert stored["question_key"] == main.response_rule_key("Naber?")
    assert stored["answer_text"] == "iyi kanka yuvarlanip gidioz"
    assert "Soru: Naber" in str(stored["text"])


def test_explicit_memory_with_time_is_plan_without_action_keyword(monkeypatch) -> None:
    fake_memory = CapturingMemory()
    now = datetime(2026, 5, 25, 12, 0, tzinfo=main.ISTANBUL_TZ)
    monkeypatch.setattr(main, "memory", fake_memory)
    monkeypatch.setattr(main.settings, "owner_wa_ids", "owner-wa")

    reply = main.store_explicit_owner_memory("owner-wa", "2 gun sonra final sinavim var unutma", now=now)

    assert reply == main.GLOBAL_MEMORY_REPLY
    assert fake_memory.added[0]["memory_kind"] == "plan"
    assert fake_memory.added[0]["expires_at_ts"] == datetime(2026, 5, 27, 23, 59, 59, tzinfo=main.ISTANBUL_TZ).timestamp()


def test_explicit_memory_with_clock_time_is_expiring_plan(monkeypatch) -> None:
    fake_memory = CapturingMemory()
    now = datetime(2026, 5, 25, 12, 0, tzinfo=main.ISTANBUL_TZ)
    monkeypatch.setattr(main, "memory", fake_memory)
    monkeypatch.setattr(main.settings, "owner_wa_ids", "owner-wa")

    reply = main.store_explicit_owner_memory("owner-wa", "Bugun saat 17:30 spor var unutma", now=now)

    assert reply == main.GLOBAL_MEMORY_REPLY
    assert fake_memory.added[0]["memory_kind"] == "plan"
    assert fake_memory.added[0]["event_at_ts"] == datetime(2026, 5, 25, 17, 30, tzinfo=main.ISTANBUL_TZ).timestamp()
    assert fake_memory.added[0]["expires_at_ts"] == datetime(2026, 5, 25, 23, 59, 59, tzinfo=main.ISTANBUL_TZ).timestamp()


def test_plan_selection_uses_generic_content_overlap(monkeypatch) -> None:
    context = (
        "[GLOBAL_PLAN: WhatsApp Memory]\n"
        "Mustafa sunu hatirlamami istedi: Bugun saat 17:30 spor var.\n\n"
        "[GLOBAL_PLAN: WhatsApp Memory]\n"
        "Mustafa sunu hatirlamami istedi: Yarin tez sunumuna hazirlanacagim."
    )
    monkeypatch.setattr(main, "memory", CapturingMemory(global_plan_context=context))

    reply = main.deterministic_reply("Tez sunumu icin ne yapacaksin?")

    assert "tez sunumuna hazirlanacagim" in reply
    assert "spor" not in reply


def test_non_owner_explicit_memory_is_not_global(monkeypatch) -> None:
    fake_memory = CapturingMemory()
    monkeypatch.setattr(main, "memory", fake_memory)
    monkeypatch.setattr(main.settings, "owner_wa_ids", "owner-wa")

    reply = main.store_explicit_owner_memory("other-wa", "30 dakika sonra AVM ye gidecegim bunu unutma")

    assert reply is None
    assert fake_memory.added == []


def test_explicit_memory_is_not_global_when_owner_list_is_empty(monkeypatch) -> None:
    fake_memory = CapturingMemory()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=main.ISTANBUL_TZ)
    monkeypatch.setattr(main, "memory", fake_memory)
    monkeypatch.setattr(main.settings, "owner_wa_ids", "")

    reply = main.store_explicit_owner_memory("any-wa", "30dk sonra AVM ye gidecegim, unutma", now=now)

    assert reply is None
    assert fake_memory.added == []
