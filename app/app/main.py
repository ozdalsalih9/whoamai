import json
import sqlite3
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "mustafa-persona:2b"
    ollama_num_ctx: int = 2048
    persona_knowledge_path: str = "/app/knowledge/mustafa_persona.md"
    persona_max_chars: int = 3500
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
    init_db()


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


def persona_system_prompt() -> str:
    knowledge = Path(settings.persona_knowledge_path).read_text(encoding="utf-8")
    if len(knowledge) > settings.persona_max_chars:
        knowledge = knowledge[: settings.persona_max_chars].rsplit("\n", 1)[0]
    return (
        "Sen WhatsApp uzerinden konusan Mustafa persona asistanisin.\n"
        "Mustafa'nin birebir kendisi oldugunu iddia etme; verilen bilgiye dayali temkinli cevap ver.\n"
        "Bilmedigin ani, olay, iliski veya dusunce uydurma.\n"
        "Cevaplari WhatsApp icin kisa, net ve dogal tut.\n\n"
        "Bilgi tabani:\n"
        f"{knowledge}"
    )


async def ask_ollama(wa_id: str, user_text: str) -> str:
    messages = [{"role": "system", "content": persona_system_prompt()}]
    messages.extend(load_history(wa_id))
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": settings.ollama_model,
        "stream": False,
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
        response.raise_for_status()


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
async def receive_webhook(request: Request) -> dict[str, str]:
    payload = await request.json()
    for message in extract_messages(payload):
        if already_processed(message["id"]):
            continue

        wa_id = message["from"]
        text = message["text"]
        normalized = normalize_text(text)

        if message["type"] != "text":
            await send_whatsapp_text(wa_id, "Simdilik sadece yazili mesajlara cevap verebiliyorum.")
            continue

        if normalized == normalize_text(settings.activation_phrase):
            set_active(wa_id, True)
            remember(wa_id, "user", text)
            reply = "Başlattım. Artık Mustafa persona ile konuşabilirsin."
            remember(wa_id, "assistant", reply)
            await send_whatsapp_text(wa_id, reply)
            continue

        if normalized in stop_phrases():
            set_active(wa_id, False)
            reply = "Tamam, bu sohbeti durdurdum. Tekrar başlatmak için 'hey mustafa, başlat' yaz."
            await send_whatsapp_text(wa_id, reply)
            continue

        if not is_active(wa_id):
            await send_whatsapp_text(wa_id, "Başlamak için 'hey mustafa, başlat' yaz.")
            continue

        remember(wa_id, "user", text)
        try:
            reply = await ask_ollama(wa_id, text)
        except httpx.HTTPError as exc:
            reply = "Şu an local modelden cevap alamıyorum. Birazdan tekrar dener misin?"
            print(json.dumps({"error": str(exc), "wa_id": wa_id}))
        remember(wa_id, "assistant", reply)
        await send_whatsapp_text(wa_id, reply)

    return {"status": "ok"}
