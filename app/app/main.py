import asyncio
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
from fastapi import FastAPI, Request
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.prompt import build_memory_extraction_prompt, build_system_prompt
from app.rag import ChromaMemory, OllamaEmbedder


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "mustafa-persona:0.6b"
    ollama_num_ctx: int = 1024
    ollama_think: bool = False
    ollama_temperature: float = 0.35
    ollama_top_p: float = 0.85
    ollama_repeat_penalty: float = 1.03
    ollama_num_predict: int = 180
    ollama_num_thread: int = 0
    ollama_keep_alive: str = "30m"
    persona_knowledge_path: str = "/app/knowledge/mustafa_persona.md"
    chroma_path: str = "/app/data/chroma"
    chroma_collection: str = "mustafa_persona"
    embedding_model: str = "nomic-embed-text"
    rag_top_k: int = 2
    rag_max_context_chars: int = 800
    rag_min_score: float = 0.35
    memory_cleanup_interval_seconds: int = 300
    memory_extraction_enabled: bool = True
    memory_extraction_model: str = "mustafa-persona:0.6b"
    memory_extraction_num_ctx: int = 512
    memory_max_chars: int = 240
    telegram_bot_token: str = ""
    telegram_polling_enabled: bool = True
    telegram_poll_interval_seconds: float = 1.0
    telegram_request_timeout: int = 50
    bot_database_path: str = "/app/data/whoamai-bot.db"
    activation_phrase: str = "hey mustafa, baslat"
    stop_phrases: str = "/stop,durdur,bitir,kapat"
    owner_telegram_ids: str = ""
    max_history_messages: int = 6
    processed_message_retention_days: int = 7


settings = Settings()
app = FastAPI(title="WhoAmAI Telegram Bot")
memory: ChromaMemory | None = None
telegram_polling_task: asyncio.Task[None] | None = None
last_expired_memory_cleanup_ts = 0.0

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
WEEKDAY_INDEX = {
    "pazartesi": 0,
    "sali": 1,
    "carsamba": 2,
    "persembe": 3,
    "cuma": 4,
    "cumartesi": 5,
    "pazar": 6,
}
PLAN_ACTION_WORDS = {
    "plan",
    "gidecegim",
    "gidiyorum",
    "gelecegim",
    "geliyorum",
    "kavusacagim",
    "bulusacagim",
    "yapacagim",
}
SELF_INTRO_WORDS = {
    "kendinden bahset",
    "kendini anlat",
    "biraz kendinden bahset",
    "mustafa kim",
    "sen kimsin",
    "seni tanimak",
    "seni taniyalim",
    "tanit kendini",
}
PROFILE_FACT_QUERIES = (
    (("kac yas", "yas kac", "yasindasin", "yasiniz kac"), "Yas", "{} yasindayim."),
    (("boyun kac", "boy kac", "kac boy"), "Boy", "Boyum {}."),
    (("kilon kac", "kilo kac", "kac kilo"), "Kilo", "Kilom {}."),
    (("hangi universite", "universiten", "nerede okudun", "nerede okuyorsun"), "Universite", "{}."),
    (("hangi sehir", "nerede yasiyorsun", "nerede yasiyor", "sehrin neresi"), "Sehir", "{}."),
    (("nerelisin", "memleket", "memleketin neresi"), "Memleket/bolge", "{}."),
    (("tam adin", "ad soyad", "ismin ne", "ad ne"), "Tam ad", "{}."),
    (("hangi takim", "takimin ne", "futbol takimin"), "Tuttugu futbol takimi", "{}."),
    (("nba", "hangi nba", "nba oyuncusu"), "Takip ettigi NBA oyuncusu", "{}."),
    (("goz rengin", "gozlerin ne renk"), "Goz rengi", "Goz rengim {}."),
)
QUERY_STOPWORDS = {
    "ben",
    "sen",
    "ne",
    "nasil",
    "nasil",
    "yapacaksin",
    "yapcan",
    "napacaksin",
    "gunu",
    "sonra",
    "var",
    "mi",
    "bir",
    "sey",
    "bisi",
    "plan",
    "planin",
    "saat",
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
UNSUPPORTED_RESPONSE_RULE_REPLY = (
    "Bu cevap kuralini kaydetmedim. Isimler icin 'Kadir benim arkadasim, unutma' gibi ogretmek daha dogru."
)
OWNER_NOT_CONFIGURED_REPLY = "Global hafiza icin OWNER_TELEGRAM_IDS ayarli degil."
NOT_OWNER_MEMORY_REPLY = "Bunu global hafizaya kaydedemem."
STATUS_REPLY = "iyi kanka yuvarlan\u0131p gidioz"
NO_PLAN_REPLY = "\u015fu anl\u0131k bi plan yok haberle\u015firiz yine"
SELF_INTRO_FALLBACK_REPLY = (
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


@dataclass(frozen=True)
class ResponseRule:
    question_text: str
    question_key: str
    answer_text: str


@dataclass(frozen=True)
class RelationshipMemory:
    person_name: str
    person_key: str
    relationship: str


def normalize_text(value: str) -> str:
    value = value.strip().lower()
    value = unicodedata.normalize("NFKC", value)
    return " ".join(value.split())


def fold_turkish(value: str) -> str:
    value = value.translate(TURKISH_CHAR_MAP)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(value.lower().split())


def user_hash(user_id: str) -> str:
    return hashlib.sha256(f"telegram:{user_id}".encode("utf-8")).hexdigest()[:32]


def now_istanbul() -> datetime:
    return datetime.now(ISTANBUL_TZ)


def owner_telegram_ids() -> set[str]:
    return {item.strip() for item in settings.owner_telegram_ids.split(",") if item.strip()}


def owner_configured() -> bool:
    return bool(owner_telegram_ids())


def is_owner_user_id(user_id: str) -> bool:
    return user_id in owner_telegram_ids()


def telegram_token_configured() -> bool:
    token = settings.telegram_bot_token.strip()
    return bool(token) and not token.startswith("change-this-")


def cleanup_expired_memories(now_ts: float, *, force: bool = False) -> None:
    global last_expired_memory_cleanup_ts
    if memory is None:
        return

    interval = max(settings.memory_cleanup_interval_seconds, 0)
    if not force and interval > 0 and now_ts - last_expired_memory_cleanup_ts < interval:
        return

    deleted = memory.delete_expired_memories(now_ts)
    last_expired_memory_cleanup_ts = now_ts
    if deleted:
        print(json.dumps({"event": "expired_memories_deleted", "count": deleted}))


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
    if mentioned_weekday(user_text) is not None:
        return True
    return bool(re.search(r"\b(\d+\s*(dakika|dk|saat|gun|gün|hafta)|yarim\s+saat)\s+sonra\b", folded))


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


def normalize_rule_text(value: str) -> str:
    stripped = value.strip(" \"'`“”‘’.,:;!?")
    return " ".join(stripped.split())


def normalize_person_name(value: str) -> str:
    cleaned = normalize_rule_text(value)
    cleaned = re.sub(r"\b(bey|hanim|abi|abla|kanka|reis)$", "", cleaned, flags=re.IGNORECASE).strip()
    return " ".join(cleaned.split())


def person_key(value: str) -> str:
    return fold_turkish(normalize_person_name(value)).strip(" ?!.")


def response_rule_key(value: str) -> str:
    return fold_turkish(normalize_rule_text(value)).strip(" ?!.")


def is_allowed_response_rule_question(question_text: str) -> bool:
    question_key = response_rule_key(question_text)
    if not question_key:
        return False
    if is_basic_status_message(question_text):
        return True
    if "?" in question_text:
        return True
    if len(question_key.split()) < 2:
        return False
    question_markers = (
        "ne",
        "nasil",
        "hangi",
        "kac",
        "kim",
        "nerede",
        "nereye",
        "neden",
        "niye",
        "mi",
        "misin",
        "musun",
        "miyim",
        "var mi",
        "planin",
    )
    return any(re.search(rf"\b{re.escape(marker)}\b", question_key) for marker in question_markers)


def parse_relationship_memory(user_text: str) -> RelationshipMemory | None:
    cleaned = strip_memory_directives(user_text)
    patterns: tuple[tuple[str, str], ...] = (
        (r"^(.+?)\s+benim\s+(?:yak[ıi]n\s+)?arkada[sş][ıi]m\b", "friend"),
        (r"^(.+?)\s+okuldan\s+arkada[sş][ıi]m\b", "friend"),
        (r"^(.+?)\s+(?:yak[ıi]n\s+)?arkada[sş][ıi]m\b", "friend"),
        (r"^(.+?)\s+kuzenim\b", "family"),
        (r"^(.+?)\s+karde[sş]im\b", "family"),
        (r"^(.+?)\s+abim\b", "family"),
        (r"^(.+?)\s+ablam\b", "family"),
    )
    for pattern, relationship in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if not match:
            continue
        name = normalize_person_name(match.group(1))
        key = person_key(name)
        if key and 1 <= len(key.split()) <= 3:
            return RelationshipMemory(person_name=name, person_key=key, relationship=relationship)
    return None


def parse_raw_response_rule(user_text: str) -> ResponseRule | None:
    cleaned = strip_memory_directives(user_text)
    patterns = (
        r"^ben\s+(.+?)\s+sorusuna\s+(.+?)\s+(?:diye|seklinde|şeklinde)\s+cevap\s+veririm\b",
        r"^(.+?)\s+sorusuna\s+(.+?)\s+(?:diye|seklinde|şeklinde)\s+cevap\s+veririm\b",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if not match:
            continue
        question_text = normalize_rule_text(match.group(1))
        answer_text = normalize_rule_text(match.group(2))
        question_key = response_rule_key(question_text)
        if question_key and answer_text:
            return ResponseRule(question_text=question_text, question_key=question_key, answer_text=answer_text)
    return None


def parse_response_rule(user_text: str) -> ResponseRule | None:
    rule = parse_raw_response_rule(user_text)
    if rule is None or not is_allowed_response_rule_question(rule.question_text):
        return None
    return rule


def parse_identity_claim(user_text: str) -> str | None:
    cleaned = normalize_rule_text(user_text)
    patterns = (
        r"^ben\s+(.+?)(?:['’]?(?:im|ım|um|üm|yim|yım|yum|yüm))?$",
        r"^ad[ıi]m\s+(.+)$",
        r"^ismim\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if not match:
            continue
        name = normalize_person_name(match.group(1))
        key = person_key(name)
        if key and 1 <= len(key.split()) <= 3:
            return key
    return None


def persona_knowledge_paths() -> list[Path]:
    configured = Path(settings.persona_knowledge_path)
    repo_path = Path(__file__).resolve().parents[2] / "knowledge" / "mustafa_persona.md"
    paths = [configured]
    if repo_path != configured:
        paths.append(repo_path)
    return paths


def read_persona_knowledge() -> str:
    for path in persona_knowledge_paths():
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


def extract_profile_fact(label: str) -> str | None:
    knowledge = read_persona_knowledge()
    if not knowledge:
        return None

    label_key = fold_turkish(label)
    for line in knowledge.splitlines():
        cleaned = line.strip()
        if not cleaned.startswith("- "):
            continue
        body = cleaned[2:]
        if ":" not in body:
            continue
        raw_label, raw_value = body.split(":", 1)
        if fold_turkish(raw_label.strip()) != label_key:
            continue
        value = re.split(r"\.\s*\(guven|\s*\(guven", raw_value.strip(), maxsplit=1)[0]
        value = value.strip(" .")
        return value or None
    return None


def profile_fact_reply(user_text: str) -> str | None:
    folded = fold_turkish(user_text)
    for triggers, label, template in PROFILE_FACT_QUERIES:
        if not any(trigger in folded for trigger in triggers):
            continue
        value = extract_profile_fact(label)
        if value is None:
            return None
        return template.format(value)
    return None


def self_intro_reply() -> str:
    name = extract_profile_fact("Tam ad") or "Mustafa Salih Ozdal"
    age = extract_profile_fact("Yas")
    city = extract_profile_fact("Sehir")
    university = extract_profile_fact("Universite")
    language = extract_profile_fact("Diller")
    team = extract_profile_fact("Tuttugu futbol takimi")

    profile_bits: list[str] = []
    if age:
        profile_bits.append(f"{age} yasindayim")
    if city:
        profile_bits.append(f"{city}'da yasiyorum")
    if university:
        profile_bits.append(f"{university} baglantim var")

    first_sentence = f"Ben {name}."
    if profile_bits:
        first_sentence = f"Ben {name}; " + ", ".join(profile_bits) + "."

    interests = [
        "Bilgisayar muhendisligi",
        "ASP.NET Core",
        "React",
        "AI sistemleri",
        "siber guvenlik",
    ]
    second_sentence = f"Ilgi alanlarim daha cok {', '.join(interests[:3])}, AI ve guvenlik tarafinda yogunlasiyor."

    extra_bits: list[str] = []
    if language:
        extra_bits.append(f"Diller: {language}")
    if team:
        extra_bits.append(f"takim olarak {team}")

    third_sentence = "Kisa, direkt ve arkadasca konusmayi severim."
    if extra_bits:
        third_sentence = f"{third_sentence} Ek olarak {', '.join(extra_bits)}."

    return " ".join([first_sentence, second_sentence, third_sentence]).strip() or SELF_INTRO_FALLBACK_REPLY


def end_of_day(value: datetime) -> datetime:
    return value.replace(hour=23, minute=59, second=59, microsecond=0)


def end_of_week(value: datetime) -> datetime:
    days_until_sunday = 6 - value.weekday()
    return end_of_day(value + timedelta(days=days_until_sunday))


def end_of_month(value: datetime) -> datetime:
    if value.month == 12:
        next_month = value.replace(year=value.year + 1, month=1, day=1)
    else:
        next_month = value.replace(month=value.month + 1, day=1)
    return next_month - timedelta(seconds=1)


def mentioned_weekday(value: str) -> str | None:
    folded = fold_turkish(value)
    for weekday in WEEKDAY_INDEX:
        if re.search(rf"\b{weekday}\b", folded):
            return weekday
    return None


def next_weekday_datetime(current: datetime, weekday: str) -> datetime:
    days_ahead = (WEEKDAY_INDEX[weekday] - current.weekday()) % 7
    target = current + timedelta(days=days_ahead)
    return target.replace(hour=0, minute=0, second=0, microsecond=0)


def mentioned_clock_time(value: str) -> tuple[int, int] | None:
    folded = fold_turkish(value)
    match = re.search(r"\b(?:saat\s*)?([01]?\d|2[0-3])(?::|\.)([0-5]\d)\b", folded)
    if match:
        return int(match.group(1)), int(match.group(2))

    match = re.search(r"\bsaat\s+([01]?\d|2[0-3])\b", folded)
    if not match:
        return None

    hour = int(match.group(1))
    if hour <= 7 and any(word in folded for word in ("aksam", "akşam", "gece")):
        hour += 12
    return hour, 0


def apply_clock_time(base: datetime, value: str) -> datetime:
    clock = mentioned_clock_time(value)
    if clock is None:
        return base
    hour, minute = clock
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def period_expiry(current: datetime, value: str) -> tuple[datetime, datetime] | None:
    folded = fold_turkish(value)
    periods = {
        "sabah": (8, 12),
        "ogle": (12, 15),
        "oglen": (12, 15),
        "aksam": (18, 23),
        "gece": (21, 23),
    }
    for word, (start_hour, end_hour) in periods.items():
        if word in folded:
            start = current.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            if start < current:
                start += timedelta(days=1)
            end = start.replace(hour=end_hour, minute=59, second=59)
            return start, end
    return None


def content_tokens(value: str) -> set[str]:
    folded = fold_turkish(value)
    tokens = set(re.findall(r"[a-z0-9']{3,}", folded))
    return {token for token in tokens if token not in QUERY_STOPWORDS}


def parse_memory_timing(user_text: str, now: datetime | None = None) -> MemoryTiming:
    current = now or now_istanbul()
    folded = fold_turkish(user_text)
    event_at: datetime | None = None
    expires_at: datetime | None = None
    weekday = mentioned_weekday(user_text)

    minute_match = re.search(r"\b(\d+)\s*(dakika|dk)\s+sonra\b", folded)
    hour_match = re.search(r"\b(\d+)\s*saat\s+sonra\b", folded)
    day_match = re.search(r"\b(\d+)\s*(gun|gün)\s+sonra\b", folded)
    week_match = re.search(r"\b(\d+)\s*hafta\s+sonra\b", folded)
    period = period_expiry(current, user_text)
    if "yarim saat sonra" in folded:
        event_at = current + timedelta(minutes=30)
        expires_at = event_at
    elif minute_match:
        event_at = current + timedelta(minutes=int(minute_match.group(1)))
        expires_at = event_at
    elif hour_match:
        event_at = current + timedelta(hours=int(hour_match.group(1)))
        expires_at = event_at
    elif day_match:
        event_at = current + timedelta(days=int(day_match.group(1)))
        expires_at = end_of_day(event_at)
    elif week_match:
        event_at = current + timedelta(weeks=int(week_match.group(1)))
        expires_at = end_of_day(event_at)
    elif "haftaya" in folded:
        event_at = current + timedelta(days=7)
        expires_at = end_of_day(event_at)
    elif "bugun" in folded:
        event_at = current
        expires_at = end_of_day(current)
    elif "yarin" in folded:
        tomorrow = current + timedelta(days=1)
        event_at = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        expires_at = end_of_day(tomorrow)
    elif weekday is not None:
        event_at = next_weekday_datetime(current, weekday)
        expires_at = end_of_day(event_at)
    elif "bu hafta" in folded:
        event_at = current
        expires_at = end_of_week(current)
    elif "ay sonu" in folded or "ayin sonu" in folded:
        event_at = current
        expires_at = end_of_month(current)
    elif period is not None:
        event_at, expires_at = period

    if event_at is not None:
        event_at = apply_clock_time(event_at, user_text)
        if expires_at is not None and event_at > expires_at:
            expires_at = end_of_day(event_at)

    if expires_at is not None:
        return MemoryTiming(memory_kind="plan", event_at=event_at, expires_at=expires_at)

    if has_remember_signal(user_text) and (
        any(char.isdigit() for char in folded)
        or any(word in folded for word in ("sabah", "ogle", "oglen", "aksam", "gece", "haftaya", "ay sonu"))
    ):
        return MemoryTiming(memory_kind="plan", event_at=None, expires_at=None)

    if any(word in folded for word in PLAN_ACTION_WORDS):
        return MemoryTiming(memory_kind="plan", event_at=None, expires_at=None)

    return MemoryTiming(memory_kind="fact", event_at=None, expires_at=None)


def build_memory_text(user_text: str) -> str:
    relationship = parse_relationship_memory(user_text)
    if relationship is not None:
        if relationship.relationship == "friend":
            return f"Mustafa sunu hatirlamami istedi: {relationship.person_name} Mustafa'nin arkadasidir."
        if relationship.relationship == "family":
            return f"Mustafa sunu hatirlamami istedi: {relationship.person_name} Mustafa'nin ailesindendir."

    rule = parse_response_rule(user_text)
    if rule is not None:
        return f"Mustafa bu soru geldiginde soyle cevap verir: Soru: {rule.question_text}. Cevap: {rule.answer_text}."

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


def select_plan_context_for_query(context: str, query: str) -> str:
    blocks = [block.strip() for block in context.split("\n\n") if block.strip()]
    if not blocks:
        return ""

    weekday = mentioned_weekday(query)
    if weekday is not None:
        for block in blocks:
            if mentioned_weekday(block) == weekday:
                return block

    folded_query = fold_turkish(query)
    query_tokens = content_tokens(query)
    best_block = ""
    best_score = 0
    for block in blocks:
        block_tokens = content_tokens(block)
        score = len(query_tokens & block_tokens)
        if score > best_score:
            best_block = block
            best_score = score
    if best_block:
        return best_block

    return blocks[0]


def active_global_plan_reply(query: str = "", now: datetime | None = None) -> str | None:
    if memory is None:
        return None

    current = now or now_istanbul()
    now_ts = current.timestamp()
    try:
        cleanup_expired_memories(now_ts)
        context = memory.retrieve_active_global_plans(top_k=5, now_ts=now_ts)
        if query and mentioned_weekday(query) is not None:
            global_context = memory.retrieve_global_memory(query, top_k=5, now_ts=now_ts)
            global_match = select_plan_context_for_query(global_context, query)
            if global_match and mentioned_weekday(global_match) == mentioned_weekday(query):
                context = f"{global_match}\n\n{context}".strip()
    except Exception as exc:
        print(json.dumps({"event": "global_plan_retrieve_failed", "error": str(exc)}))
        return None

    if not context.strip():
        return None

    context = select_plan_context_for_query(context, query)
    document = context.split("\n", 1)[1] if "\n" in context else context
    return memory_document_to_reply(document)


def learned_response_reply(user_text: str, now: datetime | None = None) -> str | None:
    if memory is None:
        return None

    query_key = response_rule_key(user_text)
    if not query_key:
        return None

    current = now or now_istanbul()
    try:
        rules = memory.get_global_response_rules(now_ts=current.timestamp())
    except Exception as exc:
        print(json.dumps({"event": "response_rule_retrieve_failed", "error": str(exc)}))
        return None

    for rule in rules:
        question_key = response_rule_key(rule.get("question_key", ""))
        question_text = rule.get("question_text", "") or question_key
        if not is_allowed_response_rule_question(question_text):
            continue
        if query_key == question_key:
            return rule.get("answer_text", "").strip() or None

    for rule in rules:
        question_key = response_rule_key(rule.get("question_key", ""))
        question_text = rule.get("question_text", "") or question_key
        if not is_allowed_response_rule_question(question_text):
            continue
        if question_key and (question_key in query_key or query_key in question_key):
            return rule.get("answer_text", "").strip() or None

    return None


def identity_relationship_reply(user_text: str, now: datetime | None = None) -> str | None:
    if memory is None:
        return None

    claimed_key = parse_identity_claim(user_text)
    if not claimed_key:
        return None

    current = now or now_istanbul()
    try:
        relationships = memory.get_global_relationships(now_ts=current.timestamp())
    except Exception as exc:
        print(json.dumps({"event": "relationship_retrieve_failed", "error": str(exc)}))
        return None

    for relationship in relationships:
        stored_key = person_key(relationship.get("person_key", ""))
        if stored_key != claimed_key:
            continue
        relation = relationship.get("relationship", "")
        if relation == "friend":
            return "naber kanka"
        if relation == "family":
            return "hos geldin"
    return None


def deterministic_reply(user_text: str) -> str | None:
    if has_remember_signal(user_text):
        return None

    learned = learned_response_reply(user_text)
    if learned is not None:
        return learned

    relationship = identity_relationship_reply(user_text)
    if relationship is not None:
        return relationship

    profile_fact = profile_fact_reply(user_text)
    if profile_fact is not None:
        return profile_fact

    if is_basic_status_message(user_text):
        return STATUS_REPLY

    if is_self_intro_query(user_text):
        return self_intro_reply()

    if is_short_praise(user_text):
        digest = hashlib.sha256(fold_turkish(user_text).encode("utf-8")).hexdigest()
        return "sa\u011fol" if int(digest[:2], 16) % 2 == 0 else "eyw"

    if is_plan_query(user_text):
        return active_global_plan_reply(user_text) or NO_PLAN_REPLY

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
                user_id TEXT PRIMARY KEY,
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
        if "wa_id" in columns and "user_id" not in columns:
            connection.execute("ALTER TABLE sessions RENAME COLUMN wa_id TO user_id")
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
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        message_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "wa_id" in message_columns and "user_id" not in message_columns:
            connection.execute("ALTER TABLE messages RENAME COLUMN wa_id TO user_id")
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
async def startup() -> None:
    global memory, telegram_polling_task
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
    if settings.telegram_polling_enabled and telegram_token_configured():
        telegram_polling_task = asyncio.create_task(telegram_polling_loop())
        print(json.dumps({"event": "telegram_polling_started"}))


@app.on_event("shutdown")
async def shutdown() -> None:
    global telegram_polling_task
    if telegram_polling_task is not None:
        telegram_polling_task.cancel()
        try:
            await telegram_polling_task
        except asyncio.CancelledError:
            pass
        telegram_polling_task = None


def is_active(user_id: str) -> bool:
    with db() as connection:
        row = connection.execute("SELECT active FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row and row["active"])


def set_active(user_id: str, active: bool) -> None:
    with db() as connection:
        connection.execute(
            """
            INSERT INTO sessions (user_id, active, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET active = excluded.active, updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, 1 if active else 0),
        )


def is_suheyla_mode(user_id: str) -> bool:
    with db() as connection:
        row = connection.execute("SELECT suheyla_mode FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row and row["suheyla_mode"])


def set_suheyla_mode(user_id: str, active: bool) -> None:
    with db() as connection:
        connection.execute(
            """
            INSERT INTO sessions (user_id, active, suheyla_mode, updated_at)
            VALUES (?, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET suheyla_mode = excluded.suheyla_mode, updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, 1 if active else 0),
        )


def remember(user_id: str, role: str, content: str) -> None:
    with db() as connection:
        connection.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )


def clear_history(user_id: str) -> None:
    with db() as connection:
        connection.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))


def already_processed(message_id: str) -> bool:
    with db() as connection:
        try:
            connection.execute("INSERT INTO processed_messages (message_id) VALUES (?)", (message_id,))
            return False
        except sqlite3.IntegrityError:
            return True


def load_history(user_id: str, exclude_latest_user_text: str | None = None) -> list[dict[str, str]]:
    with db() as connection:
        rows = connection.execute(
            """
            SELECT id, role, content
            FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, settings.max_history_messages),
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


def store_explicit_owner_memory(user_id: str, user_text: str, now: datetime | None = None) -> str | None:
    if memory is None or not is_owner_user_id(user_id) or not has_remember_signal(user_text):
        return None

    current = now or now_istanbul()
    raw_rule = parse_raw_response_rule(user_text)
    rule = parse_response_rule(user_text)
    if raw_rule is not None and rule is None:
        return UNSUPPORTED_RESPONSE_RULE_REPLY
    relationship = parse_relationship_memory(user_text)
    timing = (
        MemoryTiming(memory_kind="response_rule", event_at=None, expires_at=None)
        if rule is not None
        else MemoryTiming(memory_kind="relationship", event_at=None, expires_at=None)
        if relationship is not None
        else parse_memory_timing(user_text, now=current)
    )
    timestamp = current.isoformat()
    memory_text = build_memory_text(user_text)
    try:
        memory_id = memory.add_chat_memory(
            memory_text,
            timestamp,
            user_hash=user_hash(user_id),
            memory_kind=timing.memory_kind,
            visibility="global",
            created_at_ts=current.timestamp(),
            event_at_ts=timing.event_at.timestamp() if timing.event_at is not None else None,
            expires_at_ts=timing.expires_at.timestamp() if timing.expires_at is not None else None,
            owner_hash=user_hash(user_id),
            question_key=rule.question_key if rule is not None else None,
            question_text=rule.question_text if rule is not None else None,
            answer_text=rule.answer_text if rule is not None else None,
            person_key=relationship.person_key if relationship is not None else None,
            person_name=relationship.person_name if relationship is not None else None,
            relationship=relationship.relationship if relationship is not None else None,
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


async def ask_ollama(user_id: str, user_text: str) -> str:
    deterministic = deterministic_reply(user_text)
    if deterministic is not None:
        return deterministic

    rag_sections: list[str] = []
    if memory is not None:
        try:
            now_ts = now_istanbul().timestamp()
            cleanup_expired_memories(now_ts)
            query_embedding = memory.embedder.embed([user_text])[0]
            persona_context = memory.retrieve_persona(
                user_text,
                top_k=settings.rag_top_k,
                query_embedding=query_embedding,
            )
            global_plan_context = (
                memory.retrieve_active_global_plans(top_k=1, now_ts=now_ts) if is_plan_query(user_text) else ""
            )
            global_context = memory.retrieve_global_memory(
                user_text,
                top_k=settings.rag_top_k,
                now_ts=now_ts,
                query_embedding=query_embedding,
            )
            chat_context = memory.retrieve_chat_memory(
                user_text,
                user_hash=user_hash(user_id),
                top_k=settings.rag_top_k,
                now_ts=now_ts,
                query_embedding=query_embedding,
            )
            rag_sections = [
                section
                for section in (persona_context, global_plan_context, global_context, chat_context)
                if section.strip()
            ]
        except Exception as exc:
            print(json.dumps({"event": "rag_retrieve_failed", "error": str(exc)}))

    suheyla_mode = is_suheyla_mode(user_id)
    rag_context = "\n\n".join(rag_sections)
    messages = [{"role": "system", "content": build_system_prompt(rag_context, suheyla_mode=suheyla_mode)}]
    messages.extend(load_history(user_id, exclude_latest_user_text=user_text))
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "think": settings.ollama_think,
        "messages": messages,
        "options": ollama_options(),
        "keep_alive": settings.ollama_keep_alive,
    }

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        raw_reply = data.get("message", {}).get("content", "").strip()
        return clean_reply(raw_reply, user_text, suheyla_mode)


async def extract_and_store_memory(user_id: str, user_text: str, assistant_text: str) -> None:
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
            user_hash=user_hash(user_id),
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


def telegram_api_url(method: str) -> str:
    if not telegram_token_configured():
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


async def send_telegram_text(chat_id: str, text: str) -> None:
    payload = {
        "chat_id": chat_id,
        "text": text[:4096],
        "disable_web_page_preview": True,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(telegram_api_url("sendMessage"), json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            print(
                json.dumps(
                    {
                        "error": "telegram_send_failed",
                        "status_code": exc.response.status_code,
                        "response": exc.response.text,
                        "chat_id": chat_id,
                    },
                    ensure_ascii=False,
                )
            )
            raise


def extract_telegram_message(update: dict[str, Any]) -> dict[str, str] | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None

    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return None

    update_id = str(update.get("update_id", ""))
    message_id = str(message.get("message_id", ""))
    chat_id = str(chat["id"])
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return {
            "id": update_id or f"{chat_id}:{message_id}",
            "chat_id": chat_id,
            "text": text,
            "type": "text",
        }

    return {
        "id": update_id or f"{chat_id}:{message_id}",
        "chat_id": chat_id,
        "text": "",
        "type": "non_text",
    }


def is_activation_text(value: str) -> bool:
    folded = fold_turkish(value).strip()
    return folded == "/start" or folded.startswith("/start ") or phrase_matches(value, settings.activation_phrase)


async def process_user_text(user_id: str, text: str) -> None:
    if is_activation_text(text):
        set_active(user_id, True)
        set_suheyla_mode(user_id, False)
        clear_history(user_id)
        remember(user_id, "user", text)
        reply = "Baslattim. Artik Mustafa persona ile konusabilirsin."
        remember(user_id, "assistant", reply)
        await send_telegram_text(user_id, reply)
        return

    if is_stop_phrase(text):
        set_active(user_id, False)
        set_suheyla_mode(user_id, False)
        clear_history(user_id)
        reply = "Tamam, bu sohbeti durdurdum. Tekrar baslatmak icin /start yaz."
        await send_telegram_text(user_id, reply)
        return

    if not is_active(user_id):
        await send_telegram_text(user_id, "Baslamak icin /start yaz.")
        return

    folded_text = fold_turkish(text)
    if "ben suheyla" in folded_text:
        set_suheyla_mode(user_id, True)
    elif "ben mustafa" in folded_text or "suheyla degilim" in folded_text:
        set_suheyla_mode(user_id, False)

    remember(user_id, "user", text)
    schedule_memory_extraction = True
    memory_write_attempted = has_remember_signal(text)
    owner_memory_attempted = is_owner_user_id(user_id) and memory_write_attempted
    reply = store_explicit_owner_memory(user_id, text)
    if reply is not None:
        schedule_memory_extraction = False
    elif owner_memory_attempted:
        reply = MEMORY_STORE_FAILED_REPLY
        schedule_memory_extraction = False
    elif memory_write_attempted and not owner_configured():
        reply = OWNER_NOT_CONFIGURED_REPLY
        schedule_memory_extraction = False
    elif memory_write_attempted:
        reply = NOT_OWNER_MEMORY_REPLY
        schedule_memory_extraction = False
    else:
        reply = deterministic_reply(text)
        if reply is not None:
            schedule_memory_extraction = False
        else:
            try:
                reply = await ask_ollama(user_id, text)
            except httpx.HTTPError as exc:
                reply = "Su an local modelden cevap alamiyorum. Birazdan tekrar dener misin?"
                print(json.dumps({"error": str(exc), "user_id": user_id}))
    remember(user_id, "assistant", reply)
    if schedule_memory_extraction:
        asyncio.create_task(extract_and_store_memory(user_id, text, reply))
        print(json.dumps({"event": "memory_task_scheduled", "user_hash": user_hash(user_id)}))
    await send_telegram_text(user_id, reply)


async def handle_telegram_update(update: dict[str, Any]) -> None:
    message = extract_telegram_message(update)
    if message is None:
        return

    chat_id = message["chat_id"]
    if message["type"] != "text":
        try:
            await send_telegram_text(chat_id, "Simdilik sadece yazili mesajlara cevap verebiliyorum.")
        except httpx.HTTPError:
            pass
        return

    try:
        await process_user_text(chat_id, message["text"])
    except httpx.HTTPError:
        pass


async def telegram_polling_loop() -> None:
    offset: int | None = None
    while True:
        try:
            params: dict[str, Any] = {
                "timeout": settings.telegram_request_timeout,
                "allowed_updates": json.dumps(["message"]),
            }
            if offset is not None:
                params["offset"] = offset
            async with httpx.AsyncClient(timeout=settings.telegram_request_timeout + 10) as client:
                response = await client.get(telegram_api_url("getUpdates"), params=params)
                response.raise_for_status()
                data = response.json()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(json.dumps({"event": "telegram_polling_failed", "error": str(exc)}))
            await asyncio.sleep(max(settings.telegram_poll_interval_seconds, 1.0))
            continue

        for update in data.get("result", []):
            if not isinstance(update, dict):
                continue
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1
                processed_key = f"telegram:{update_id}"
            else:
                processed_key = f"telegram:{json.dumps(update, sort_keys=True)}"
            if already_processed(processed_key):
                continue
            await handle_telegram_update(update)

        await asyncio.sleep(settings.telegram_poll_interval_seconds)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/telegram")
async def receive_telegram_webhook(request: Request) -> dict[str, str]:
    payload = await request.json()
    update_id = payload.get("update_id")
    processed_key = f"telegram:{update_id}" if update_id is not None else json.dumps(payload, sort_keys=True)
    if not already_processed(processed_key):
        await handle_telegram_update(payload)
    return {"status": "ok"}
