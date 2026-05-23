import json
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime
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
    persona_knowledge_path: str = "/app/knowledge/mustafa_persona.md"
    chroma_path: str = "/app/data/chroma"
    chroma_collection: str = "mustafa_persona"
    embedding_model: str = "nomic-embed-text"
    rag_top_k: int = 3
    rag_max_context_chars: int = 1200
    rag_min_score: float = 0.25
    memory_extraction_enabled: bool = True
    memory_extraction_model: str = "mustafa-persona:2b"
    memory_extraction_num_ctx: int = 512
    memory_max_chars: int = 240
    whatsapp_verify_token: str
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    whatsapp_graph_api_version: str = "v25.0"
    bot_database_path: str = "/app/data/whoamai-bot.db"
    activation_phrase: str = "hey mustafa, başlat"
    stop_phrases: str = "durdur,bitir,kapat"
    max_history_messages: int = 10


settings = Settings()
app = FastAPI(title="WhoAmAI WhatsApp Bot")
memory: ChromaMemory | None = None


def normalize_text(value: str) -> str:
    value = value.strip().lower()
    value = unicodedata.normalize("NFKC", value)
    return " ".join(value.split())


def stop_phrases() -> set[str]:
    return {normalize_text(item) for item in settings.stop_phrases.split(",") if item.strip()}


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
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
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
        if memory.count() == 0:
            count = memory.reset_from_markdown(settings.persona_knowledge_path)
            print(json.dumps({"event": "rag_indexed", "chunks": count}))
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


def remember(wa_id: str, role: str, content: str) -> None:
    with db() as connection:
        connection.execute(
            "INSERT INTO messages (wa_id, role, content) VALUES (?, ?, ?)",
            (wa_id, role, content),
        )


def already_processed(message_id: str) -> bool:
    with db() as connection:
        try:
            connection.execute("INSERT INTO processed_messages (message_id) VALUES (?)", (message_id,))
            return False
        except sqlite3.IntegrityError:
            return True


def load_history(wa_id: str) -> list[dict[str, str]]:
    with db() as connection:
        rows = connection.execute(
            """
            SELECT role, content
            FROM messages
            WHERE wa_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (wa_id, settings.max_history_messages),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


async def ask_ollama(wa_id: str, user_text: str) -> str:
    rag_context = ""
    if memory is not None:
        try:
            rag_context = memory.retrieve(user_text, top_k=settings.rag_top_k)
        except Exception as exc:
            print(json.dumps({"event": "rag_retrieve_failed", "error": str(exc)}))

    messages = [{"role": "system", "content": build_system_prompt(rag_context)}]
    messages.extend(load_history(wa_id))
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "think": settings.ollama_think,
        "messages": messages,
        "options": {
            "num_ctx": settings.ollama_num_ctx,
            "temperature": 0.55,
            "top_p": 0.9,
        },
    }

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "").strip() or "Su an cevap uretemedim."


async def extract_and_store_memory(user_text: str, assistant_text: str) -> None:
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
    none_candidate = extracted.upper().strip(".。! ")
    if not extracted or none_candidate == "NONE":
        print(json.dumps({"event": "memory_skipped"}))
        return

    if len(extracted) > settings.memory_max_chars:
        extracted = extracted[: settings.memory_max_chars].rsplit(" ", 1)[0].strip()

    timestamp = datetime.now(ZoneInfo("Europe/Istanbul")).isoformat()
    try:
        memory_id = memory.add_chat_memory(extracted, timestamp)
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
        normalized = normalize_text(text)

        if message["type"] != "text":
            try:
                await send_whatsapp_text(wa_id, "Simdilik sadece yazili mesajlara cevap verebiliyorum.")
            except httpx.HTTPError:
                pass
            continue

        if normalized == normalize_text(settings.activation_phrase):
            set_active(wa_id, True)
            remember(wa_id, "user", text)
            reply = "Başlattım. Artık Mustafa persona ile konuşabilirsin."
            remember(wa_id, "assistant", reply)
            try:
                await send_whatsapp_text(wa_id, reply)
            except httpx.HTTPError:
                pass
            continue

        if normalized in stop_phrases():
            set_active(wa_id, False)
            reply = "Tamam, bu sohbeti durdurdum. Tekrar başlatmak için 'hey mustafa, başlat' yaz."
            try:
                await send_whatsapp_text(wa_id, reply)
            except httpx.HTTPError:
                pass
            continue

        if not is_active(wa_id):
            try:
                await send_whatsapp_text(wa_id, "Başlamak için 'hey mustafa, başlat' yaz.")
            except httpx.HTTPError:
                pass
            continue

        remember(wa_id, "user", text)
        try:
            reply = await ask_ollama(wa_id, text)
        except httpx.HTTPError as exc:
            reply = "Şu an local modelden cevap alamıyorum. Birazdan tekrar dener misin?"
            print(json.dumps({"error": str(exc), "wa_id": wa_id}))
        remember(wa_id, "assistant", reply)
        background_tasks.add_task(extract_and_store_memory, text, reply)
        print(json.dumps({"event": "memory_task_scheduled", "wa_id": wa_id}))
        try:
            await send_whatsapp_text(wa_id, reply)
        except httpx.HTTPError:
            pass

    return {"status": "ok"}
