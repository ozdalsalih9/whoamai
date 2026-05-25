import hashlib
import json
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic_settings import BaseSettings

from app.prompt import build_memory_extraction_prompt, build_system_prompt
from app.rag import ChromaMemory, OllamaEmbedder


class Settings(BaseSettings):
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "mustafa-persona:0.6b"
    ollama_num_ctx: int = 1024
    ollama_think: bool = False
    ollama_temperature: float = 0.35
    ollama_top_p: float = 0.85
    ollama_repeat_penalty: float = 1.03
    ollama_num_predict: int = 180
    ollama_num_thread: int = 0
    persona_knowledge_path: str = "/app/knowledge/mustafa_persona.md"
    chroma_path: str = "/app/data/chroma"
    chroma_collection: str = "mustafa_persona"
    embedding_model: str = "nomic-embed-text"
    rag_top_k: int = 2
    rag_max_context_chars: int = 800
    rag_min_score: float = 0.35
    memory_extraction_enabled: bool = True
    memory_extraction_model: str = "mustafa-persona:0.6b"
    memory_extraction_num_ctx: int = 512
    memory_max_chars: int = 240
    whatsapp_verify_token: str
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    whatsapp_graph_api_version: str = "v25.0"
    bot_database_path: str = "/app/data/whoamai-bot.db"
    activation_phrase: str = "hey mustafa, baslat"
    stop_phrases: str = "durdur,bitir,kapat"
    owner_wa_ids: str = ""
    max_history_messages: int = 6
    processed_message_retention_days: int = 7


settings = Settings()
app = FastAPI(title="WhoAmAI WhatsApp Bot")
memory: ChromaMemory | None = None

TURKISH_CHAR_MAP = str.maketrans(
    {
        "\u0131": "i",
        "\u0130": "I",
        "\u011f": "g",
        "\u011e": "G",
        "\u00fc": "u",
        "\u00dc": "U",
        "\u015f": "s",
        "\u015e": "S",
        "\u00f6": "o",
        "\u00d6": "O",
        "\u00e7": "c",
        "\u00c7": "C",
    }
)
MEMORY_SIGNAL_WORDS = {
    "artik",
    "bundan sonra",
    "bundan boyle",
    "yarin",
    "haftaya",
    "bugun",
    "bu gece",
    "bu hafta",
    "gidiyorum",
    "gidecegim",
    "geliyorum",
    "gelecegim",
    "tasiniyorum",
    "basladim",
    "baslayacagim",
    "biraktim",
    "deniyorum",
    "deneyecegim",
    "istiyorum",
    "sevmiyorum",
    "seviyorum",
    "tercih ediyorum",
    "planim",
    "projem",
    "kiz arkadasim",
    "suheyla",
    "aklinda tut",
    "unutma",
    "not al",
    "hatirla",
    "kaydet",
}
BASIC_STATUS_TRIGGERS = {
    "naber",
    "ne haber",
    "nasilsin",
    "napiyon",
    "napion",
    "ne yapiyorsun",
}
STATUS_ALLOWED_WORDS = {
    "naber",
    "ne",
    "haber",
    "nasilsin",
    "napiyon",
    "napion",
    "yapiyorsun",
    "kanka",
    "knk",
    "reis",
}
PRAISE_WORDS = {
    "cok iyi",
    "guzel olmus",
    "harika",
    "super",
    "mukemmel",
    "eline saglik",
    "adamsin",
    "kralsin",
    "efsane",
    "basarili",
}
REMEMBER_SIGNAL_WORDS = {
    "aklinda tut",
    "unutma",
    "not al",
    "hatirla",
    "kaydet",
}
PLAN_QUERY_WORDS = {
    "planin var mi",
    "plan var mi",
    "bir seyler yapalim",
    "biseyler yapalim",
    "bisi yapalim",
    "bir sey yapalim",
    "ne yapacaksin",
    "napacaksin",
    "n'apacaksin",
    "ne yapcan",
    "nereye gideceksin",
}
SELF_INTRO_WORDS = {
    "kendinden bahset",
    "kendini anlat",
    "biraz kendinden bahset",
    "mustafa kim",
    "sen kimsin",
}
BANNED_REPLY_FRAGMENTS = (
    "ben bir yapay zeka",
    "bir yapay zeka",
    "yapay zeka olarak",
    "asistanim",
    "persona asistani",
    "gercek mustafa",
    "bilincim var",
    "duygularim var",
    "ozledim",
    "asigim",
    "kiskandim",
    "askim",
    "canim",
    "cicim",
    "sevgilim",
    "sana baska nasil yardimci olabilirim",
    "baska nasil yardimci olabilirim",
    "yardimci olabilir miyim",
    "how else can i help",
    "anything else i can help",
)
ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
GLOBAL_MEMORY_REPLY = "Tamam, bunu not aldim."
MEMORY_STORE_FAILED_REPLY = "Su an not alamadim."
STATUS_REPLY = "iyi kanka yuvarlan\u0131p gidioz"
NO_PLAN_REPLY = "\u015fu anl\u0131k bi plan yok haberle\u015firiz yine"
SELF_INTRO_REPLY = (
    "Mustafa; teknik konularda direkt, sosyal konularda k\u0131sa ve samimi cevap veren, "
    "proje ve AI taraf\u0131na odakl\u0131 biri."
)
MEMORY_TEXT_PREFIX = "Mustafa sunu hatirlamami istedi:"
DIRECTIVE_PATTERNS = (
    r"\b(bunu\s+)?unutma\b",
    r"\b(bunu\s+)?akl[\u0131i]nda tut\b",
    r"\b(bunu\s+)?not al\b",
    r"\b(bunu\s+)?hat[\u0131i]rla\b",
    r"\b(bunu\s+)?kaydet\b",
)
TRAILING_AI_HELP_RE = re.compile(
    r"(sana\s+)?baska\s+nasil\s+yardimci\s+olabilirim.*$|"
    r"yardimci\s+olabilir\s+miyim.*$|"
    r"how\s+else\s+can\s+i\s+help.*$|"
    r"anything\s+else\s+i\s+can\s+help.*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MemoryTiming:
    memory_kind: str
    event_at: datetime | None
    expires_at: datetime | None


def normalize_text(value: str) -> str:
    value = value.strip().lower()
    value = unicodedata.normalize("NFKC", value)
    return " ".join(value.split())


def fold_turkish(value: str) -> str:
    value = value.translate(TURKISH_CHAR_MAP)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(value.lower().split())


def user_hash(wa_id: str) -> str:
    return hashlib.sha256(f"whatsapp:{wa_id}".encode("utf-8")).hexdigest()[:32]


def now_istanbul() -> datetime:
    return datetime.now(ISTANBUL_TZ)


def owner_wa_ids() -> set[str]:
    return {item.strip() for item in settings.owner_wa_ids.split(",") if item.strip()}


def is_owner_wa_id(wa_id: str) -> bool:
    owners = owner_wa_ids()
    return not owners or wa_id in owners


def has_remember_signal(user_text: str) -> bool:
    folded = fold_turkish(user_text)
    return any(signal in folded for signal in REMEMBER_SIGNAL_WORDS)


def is_basic_status_message(user_text: str) -> bool:
    folded = fold_turkish(user_text).strip(" ?!.")
    words = re.findall(r"[a-z0-9']+", folded)
    if not words or len(words) > 4 or any(word not in STATUS_ALLOWED_WORDS for word in words):
        return False
    return any(trigger == folded or trigger in folded for trigger in BASIC_STATUS_TRIGGERS)


def is_short_praise(user_text: str) -> bool:
    folded = fold_turkish(user_text)
    if "?" in user_text or len(folded) > 90:
        return False
    return any(word in folded for word in PRAISE_WORDS)


def is_plan_query(user_text: str) -> bool:
    folded = fold_turkish(user_text)
    if has_remember_signal(user_text):
        return False
    if any(word in folded for word in PLAN_QUERY_WORDS):
        return True
    return bool(re.search(r"\b(\d+\s*(dakika|dk|saat)|yarim\s+saat)\s+sonra\b", folded))


def is_self_intro_query(user_text: str) -> bool:
    folded = fold_turkish(user_text)
    return any(word in folded for word in SELF_INTRO_WORDS)


def strip_memory_directives(user_text: str) -> str:
    cleaned = " ".join(user_text.strip().split())
    for pattern in DIRECTIVE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" .,!?\t\n")


def end_of_day(value: datetime) -> datetime:
    return value.replace(hour=23, minute=59, second=59, microsecond=0)


def parse_memory_timing(user_text: str, now: datetime | None = None) -> MemoryTiming:
    current = now or now_istanbul()
    folded = fold_turkish(user_text)
    event_at: datetime | None = None
    expires_at: datetime | None = None

    minute_match = re.search(r"\b(\d+)\s*(dakika|dk)\s+sonra\b", folded)
    hour_match = re.search(r"\b(\d+)\s*saat\s+sonra\b", folded)
    if "yarim saat sonra" in folded:
        event_at = current + timedelta(minutes=30)
        expires_at = event_at
    elif minute_match:
        event_at = current + timedelta(minutes=int(minute_match.group(1)))
        expires_at = event_at
    elif hour_match:
        event_at = current + timedelta(hours=int(hour_match.group(1)))
        expires_at = event_at
    elif "bugun" in folded:
        event_at = current
        expires_at = end_of_day(current)
    elif "yarin" in folded:
        tomorrow = current + timedelta(days=1)
        event_at = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        expires_at = end_of_day(tomorrow)

    if expires_at is not None:
        return MemoryTiming(memory_kind="plan", event_at=event_at, expires_at=expires_at)

    if any(word in folded for word in ("plan", "gidecegim", "gidiyorum", "gelecegim", "geliyorum")):
        return MemoryTiming(memory_kind="plan", event_at=None, expires_at=None)

    return MemoryTiming(memory_kind="fact", event_at=None, expires_at=None)


def build_memory_text(user_text: str) -> str:
    cleaned = strip_memory_directives(user_text)
    if not cleaned:
        cleaned = "kisa bir not"
    if cleaned.endswith((".", "!", "?")):
        cleaned = cleaned[:-1].strip()
    return f"{MEMORY_TEXT_PREFIX} {cleaned}."


def memory_document_to_reply(document: str) -> str:
    text = " ".join(document.split())
    if text.startswith(MEMORY_TEXT_PREFIX):
        text = text[len(MEMORY_TEXT_PREFIX) :].strip()
    text = strip_memory_directives(text)
    text = re.sub(
        r"^(normalde\s+)?(\d+\s*(dakika|dk|saat)\s+sonra|yar[\u0131i]m\s+saat\s+sonra)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    if not text:
        return NO_PLAN_REPLY
    if text[-1] not in ".!?":
        text += "."
    return text


def active_global_plan_reply(now: datetime | None = None) -> str | None:
    if memory is None:
        return None

    current = now or now_istanbul()
    now_ts = current.timestamp()
    try:
        memory.delete_expired_memories(now_ts)
        context = memory.retrieve_active_global_plans(top_k=1, now_ts=now_ts)
    except Exception as exc:
        print(json.dumps({"event": "global_plan_retrieve_failed", "error": str(exc)}))
        return None

    if not context.strip():
        return None

    document = context.split("\n", 1)[1] if "\n" in context else context
    return memory_document_to_reply(document)


def deterministic_reply(user_text: str) -> str | None:
    if has_remember_signal(user_text):
        return None

    if is_basic_status_message(user_text):
        return STATUS_REPLY

    if is_self_intro_query(user_text):
        return SELF_INTRO_REPLY

    if is_short_praise(user_text):
        digest = hashlib.sha256(fold_turkish(user_text).encode("utf-8")).hexdigest()
        return "sa\u011fol" if int(digest[:2], 16) % 2 == 0 else "eyw"

    if is_plan_query(user_text):
        return active_global_plan_reply() or NO_PLAN_REPLY

    return None


def fallback_memory_candidate(user_text: str) -> str | None:
    cleaned = " ".join(user_text.strip().split())
    if len(cleaned) < 8:
        return None

    folded = fold_turkish(cleaned)
    if not any(signal in folded for signal in MEMORY_SIGNAL_WORDS):
        return None

    lowered = cleaned[:1].lower() + cleaned[1:]
    if lowered.endswith((".", "!", "?")):
        lowered = lowered[:-1]
    return f"Kullanici sunu belirtti: {lowered}."


def phrase_matches(value: str, phrase: str) -> bool:
    return normalize_text(value) == normalize_text(phrase) or fold_turkish(value) == fold_turkish(phrase)


def is_stop_phrase(value: str) -> bool:
    return any(phrase_matches(value, item) for item in settings.stop_phrases.split(",") if item.strip())


@contextmanager
def db() -> Any:
    path = Path(settings.bot_database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                wa_id TEXT PRIMARY KEY,
                active INTEGER NOT NULL DEFAULT 0,
                suheyla_mode INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "suheyla_mode" not in columns:
            connection.execute("ALTER TABLE sessions ADD COLUMN suheyla_mode INTEGER NOT NULL DEFAULT 0")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wa_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cutoff = f"-{settings.processed_message_retention_days} days"
        connection.execute(
            "DELETE FROM processed_messages WHERE created_at < datetime('now', ?)",
            (cutoff,),
        )


@app.on_event("startup")
def startup() -> None:
    global memory
    init_db()
    embedder = OllamaEmbedder(settings.ollama_base_url, settings.embedding_model)
    memory = ChromaMemory(
        persist_path=settings.chroma_path,
        collection_name=settings.chroma_collection,
        embedder=embedder,
        max_context_chars=settings.rag_max_context_chars,
        min_score=settings.rag_min_score,
    )
    try:
        if memory.count_by_scope("persona") == 0:
            count = memory.reset_from_markdown(settings.persona_knowledge_path)
            print(json.dumps({"event": "rag_indexed", "chunks": count, "scope": "persona"}))
    except Exception as exc:
        print(json.dumps({"event": "rag_index_failed", "error": str(exc)}))


def is_active(wa_id: str) -> bool:
    with db() as connection:
        row = connection.execute("SELECT active FROM sessions WHERE wa_id = ?", (wa_id,)).fetchone()
        return bool(row and row["active"])


def set_active(wa_id: str, active: bool) -> None:
    with db() as connection:
        connection.execute(
            """
            INSERT INTO sessions (wa_id, active, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(wa_id) DO UPDATE SET active = excluded.active, updated_at = CURRENT_TIMESTAMP
            """,
            (wa_id, 1 if active else 0),
        )


def is_suheyla_mode(wa_id: str) -> bool:
    with db() as connection:
        row = connection.execute("SELECT suheyla_mode FROM sessions WHERE wa_id = ?", (wa_id,)).fetchone()
        return bool(row and row["suheyla_mode"])


def set_suheyla_mode(wa_id: str, active: bool) -> None:
    with db() as connection:
        connection.execute(
            """
            INSERT INTO sessions (wa_id, active, suheyla_mode, updated_at)
            VALUES (?, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(wa_id) DO UPDATE SET suheyla_mode = excluded.suheyla_mode, updated_at = CURRENT_TIMESTAMP
            """,
            (wa_id, 1 if active else 0),
        )


def remember(wa_id: str, role: str, content: str) -> None:
    with db() as connection:
        connection.execute(
            "INSERT INTO messages (wa_id, role, content) VALUES (?, ?, ?)",
            (wa_id, role, content),
        )


def clear_history(wa_id: str) -> None:
    with db() as connection:
        connection.execute("DELETE FROM messages WHERE wa_id = ?", (wa_id,))


def already_processed(message_id: str) -> bool:
    with db() as connection:
        try:
            connection.execute("INSERT INTO processed_messages (message_id) VALUES (?)", (message_id,))
            return False
        except sqlite3.IntegrityError:
            return True


def load_history(wa_id: str, exclude_latest_user_text: str | None = None) -> list[dict[str, str]]:
    with db() as connection:
        rows = connection.execute(
            """
            SELECT id, role, content
            FROM messages
            WHERE wa_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (wa_id, settings.max_history_messages),
        ).fetchall()
    history: list[dict[str, str]] = []
    excluded = normalize_text(exclude_latest_user_text) if exclude_latest_user_text else None
    ordered_rows = list(reversed(rows))
    latest_excluded_id = None
    if excluded:
        for row in reversed(ordered_rows):
            if row["role"] == "user" and normalize_text(str(row["content"])) == excluded:
                latest_excluded_id = row["id"]
                break

    for row in ordered_rows:
        role = str(row["role"])
        if role not in {"user", "assistant"}:
            continue
        content = " ".join(str(row["content"]).split())
        if not content:
            continue
        if latest_excluded_id is not None and row["id"] == latest_excluded_id:
            continue
        if len(content) > 280:
            content = content[:280].rsplit(" ", 1)[0].strip()
        history.append({"role": role, "content": content})
    return history


def store_explicit_owner_memory(wa_id: str, user_text: str, now: datetime | None = None) -> str | None:
    if memory is None or not is_owner_wa_id(wa_id) or not has_remember_signal(user_text):
        return None

    current = now or now_istanbul()
    timing = parse_memory_timing(user_text, now=current)
    timestamp = current.isoformat()
    memory_text = build_memory_text(user_text)
    try:
        memory_id = memory.add_chat_memory(
            memory_text,
            timestamp,
            user_hash=user_hash(wa_id),
            memory_kind=timing.memory_kind,
            visibility="global",
            created_at_ts=current.timestamp(),
            event_at_ts=timing.event_at.timestamp() if timing.event_at is not None else None,
            expires_at_ts=timing.expires_at.timestamp() if timing.expires_at is not None else None,
            owner_hash=user_hash(wa_id),
        )
    except Exception as exc:
        print(json.dumps({"event": "owner_memory_store_failed", "error": str(exc)}, ensure_ascii=False))
        return None

    print(
        json.dumps(
            {
                "event": "owner_memory_stored",
                "id": memory_id,
                "memory": memory_text,
                "memory_kind": timing.memory_kind,
                "expires_at": timing.expires_at.isoformat() if timing.expires_at is not None else None,
            },
            ensure_ascii=False,
        )
    )
    return GLOBAL_MEMORY_REPLY


def clean_reply(reply: str, user_text: str, suheyla_mode: bool) -> str:
    cleaned = " ".join(reply.split())
    if not cleaned:
        return "Su an cevap uretemedim."
    cleaned = TRAILING_AI_HELP_RE.sub("", cleaned).strip(" .,!?\t\n")
    if not cleaned:
        return "Bunu net bilmiyorum."

    user_folded = fold_turkish(user_text)
    allow_suheyla = suheyla_mode or "suheyla" in user_folded
    sentences = [part.strip() for part in cleaned.replace("!", ".").replace("?", ".").split(".")]
    kept: list[str] = []
    seen: set[str] = set()

    for sentence in sentences:
        if not sentence:
            continue
        folded = fold_turkish(sentence)
        if any(fragment in folded for fragment in BANNED_REPLY_FRAGMENTS):
            continue
        if not allow_suheyla and "suheyla" in folded:
            continue
        if folded in seen:
            continue
        seen.add(folded)
        kept.append(sentence)

    if not kept:
        return "Bunu net bilmiyorum."

    result = ". ".join(kept[:3]).strip()
    if result and result[-1] not in ".!?":
        result += "."
    return result


def ollama_options() -> dict[str, int | float]:
    options: dict[str, int | float] = {
        "num_ctx": settings.ollama_num_ctx,
        "temperature": settings.ollama_temperature,
        "top_p": settings.ollama_top_p,
        "repeat_penalty": settings.ollama_repeat_penalty,
        "num_predict": settings.ollama_num_predict,
    }
    if settings.ollama_num_thread > 0:
        options["num_thread"] = settings.ollama_num_thread
    return options


async def ask_ollama(wa_id: str, user_text: str) -> str:
    deterministic = deterministic_reply(user_text)
    if deterministic is not None:
        return deterministic

    rag_sections: list[str] = []
    if memory is not None:
        try:
            now_ts = now_istanbul().timestamp()
            memory.delete_expired_memories(now_ts)
            persona_context = memory.retrieve_persona(user_text, top_k=settings.rag_top_k)
            global_plan_context = (
                memory.retrieve_active_global_plans(top_k=1, now_ts=now_ts) if is_plan_query(user_text) else ""
            )
            global_context = memory.retrieve_global_memory(
                user_text,
                top_k=settings.rag_top_k,
                now_ts=now_ts,
            )
            chat_context = memory.retrieve_chat_memory(
                user_text,
                user_hash=user_hash(wa_id),
                top_k=settings.rag_top_k,
                now_ts=now_ts,
            )
            rag_sections = [
                section
                for section in (persona_context, global_plan_context, global_context, chat_context)
                if section.strip()
            ]
        except Exception as exc:
            print(json.dumps({"event": "rag_retrieve_failed", "error": str(exc)}))

    suheyla_mode = is_suheyla_mode(wa_id)
    rag_context = "\n\n".join(rag_sections)
    messages = [{"role": "system", "content": build_system_prompt(rag_context, suheyla_mode=suheyla_mode)}]
    messages.extend(load_history(wa_id, exclude_latest_user_text=user_text))
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "think": settings.ollama_think,
        "messages": messages,
        "options": ollama_options(),
    }

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        raw_reply = data.get("message", {}).get("content", "").strip()
        return clean_reply(raw_reply, user_text, suheyla_mode)


async def extract_and_store_memory(wa_id: str, user_text: str, assistant_text: str) -> None:
    print(json.dumps({"event": "memory_task_started"}))
    if not settings.memory_extraction_enabled or memory is None:
        print(
            json.dumps(
                {
                    "event": "memory_disabled",
                    "enabled": settings.memory_extraction_enabled,
                    "memory_ready": memory is not None,
                }
            )
        )
        return

    payload = {
        "model": settings.memory_extraction_model,
        "stream": False,
        "think": False,
        "messages": [
            {
                "role": "user",
                "content": build_memory_extraction_prompt(user_text, assistant_text),
            }
        ],
        "options": {
            "num_ctx": settings.memory_extraction_num_ctx,
            "temperature": 0,
            "top_p": 0.7,
            "repeat_penalty": settings.ollama_repeat_penalty,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        print(json.dumps({"event": "memory_extract_failed", "error": str(exc)}))
        return

    extracted = data.get("message", {}).get("content", "").strip()
    extracted = extracted.strip("\"'` \n\t")
    none_candidate = extracted.upper().strip(".! ")
    if not extracted or none_candidate == "NONE":
        fallback = fallback_memory_candidate(user_text)
        if fallback is None:
            print(json.dumps({"event": "memory_skipped"}))
            return
        extracted = fallback
        print(json.dumps({"event": "memory_fallback_used", "memory": extracted}, ensure_ascii=False))

    if len(extracted) > settings.memory_max_chars:
        extracted = extracted[: settings.memory_max_chars].rsplit(" ", 1)[0].strip()

    current = now_istanbul()
    timing = parse_memory_timing(user_text, now=current)
    timestamp = current.isoformat()
    try:
        memory_id = memory.add_chat_memory(
            extracted,
            timestamp,
            user_hash=user_hash(wa_id),
            memory_kind=timing.memory_kind,
            visibility="private",
            created_at_ts=current.timestamp(),
            event_at_ts=timing.event_at.timestamp() if timing.event_at is not None else None,
            expires_at_ts=timing.expires_at.timestamp() if timing.expires_at is not None else None,
        )
    except Exception as exc:
        print(json.dumps({"event": "memory_store_failed", "error": str(exc), "memory": extracted}, ensure_ascii=False))
        return

    print(json.dumps({"event": "memory_stored", "id": memory_id, "memory": extracted}, ensure_ascii=False))


async def send_whatsapp_text(to: str, text: str) -> None:
    url = (
        f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/"
        f"{settings.whatsapp_phone_number_id}/messages"
    )
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text[:4000]},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers=headers, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            print(
                json.dumps(
                    {
                        "error": "whatsapp_send_failed",
                        "status_code": exc.response.status_code,
                        "response": exc.response.text,
                        "wa_id": to,
                    }
                )
            )
            raise


def extract_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    extracted: list[dict[str, str]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                if message.get("type") != "text":
                    extracted.append(
                        {
                            "id": message.get("id", ""),
                            "from": message.get("from", ""),
                            "text": "",
                            "type": message.get("type", "unknown"),
                        }
                    )
                    continue
                extracted.append(
                    {
                        "id": message.get("id", ""),
                        "from": message.get("from", ""),
                        "text": message.get("text", {}).get("body", ""),
                        "type": "text",
                    }
                )
    return [item for item in extracted if item["id"] and item["from"]]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/webhook/whatsapp", response_class=PlainTextResponse)
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> str:
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return hub_challenge
    raise HTTPException(status_code=403, detail="Invalid verify token")


@app.post("/webhook/whatsapp")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    payload = await request.json()
    for message in extract_messages(payload):
        if already_processed(message["id"]):
            continue

        wa_id = message["from"]
        text = message["text"]

        if message["type"] != "text":
            try:
                await send_whatsapp_text(wa_id, "Simdilik sadece yazili mesajlara cevap verebiliyorum.")
            except httpx.HTTPError:
                pass
            continue

        if phrase_matches(text, settings.activation_phrase):
            set_active(wa_id, True)
            set_suheyla_mode(wa_id, False)
            clear_history(wa_id)
            remember(wa_id, "user", text)
            reply = "Baslattim. Artik Mustafa persona ile konusabilirsin."
            remember(wa_id, "assistant", reply)
            try:
                await send_whatsapp_text(wa_id, reply)
            except httpx.HTTPError:
                pass
            continue

        if is_stop_phrase(text):
            set_active(wa_id, False)
            set_suheyla_mode(wa_id, False)
            clear_history(wa_id)
            reply = "Tamam, bu sohbeti durdurdum. Tekrar baslatmak icin 'hey mustafa, baslat' yaz."
            try:
                await send_whatsapp_text(wa_id, reply)
            except httpx.HTTPError:
                pass
            continue

        if not is_active(wa_id):
            try:
                await send_whatsapp_text(wa_id, "Baslamak icin 'hey mustafa, baslat' yaz.")
            except httpx.HTTPError:
                pass
            continue

        folded_text = fold_turkish(text)
        if "ben suheyla" in folded_text:
            set_suheyla_mode(wa_id, True)
        elif "ben mustafa" in folded_text or "suheyla degilim" in folded_text:
            set_suheyla_mode(wa_id, False)

        remember(wa_id, "user", text)
        schedule_memory_extraction = True
        owner_memory_attempted = is_owner_wa_id(wa_id) and has_remember_signal(text)
        reply = store_explicit_owner_memory(wa_id, text)
        if reply is not None:
            schedule_memory_extraction = False
        elif owner_memory_attempted:
            reply = MEMORY_STORE_FAILED_REPLY
            schedule_memory_extraction = False
        else:
            reply = deterministic_reply(text)
            if reply is not None:
                schedule_memory_extraction = False
            else:
                try:
                    reply = await ask_ollama(wa_id, text)
                except httpx.HTTPError as exc:
                    reply = "Su an local modelden cevap alamiyorum. Birazdan tekrar dener misin?"
                    print(json.dumps({"error": str(exc), "wa_id": wa_id}))
        remember(wa_id, "assistant", reply)
        if schedule_memory_extraction:
            background_tasks.add_task(extract_and_store_memory, wa_id, text, reply)
            print(json.dumps({"event": "memory_task_scheduled", "user_hash": user_hash(wa_id)}))
        try:
            await send_whatsapp_text(wa_id, reply)
        except httpx.HTTPError:
            pass

    return {"status": "ok"}
