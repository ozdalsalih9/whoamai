# Mustafa Persona WhatsApp Bot MVP

This project runs a personal Mustafa persona bot over WhatsApp using:

- Ollama for local LLM inference
- Meta WhatsApp Cloud API for WhatsApp messages
- A small FastAPI webhook service
- ChromaDB RAG over `knowledge/mustafa_persona.md`
- SQLite for WhatsApp session state, short chat history, and processed message IDs

Open WebUI is no longer required for the main flow. If `localhost:3000` shows an Open WebUI admin screen, that is from the earlier UI approach and can be ignored for the WhatsApp bot.

## Current Model Defaults

- Default model on shared 4 vCPU VPS: `mustafa-persona:0.6b`
- Default base model: `qwen3:0.6b`
- Medium model: `mustafa-persona:2b`
- Medium base model: `qwen3.5:2b`
- Higher-quality model: `mustafa-persona:4b`
- Higher-quality base model: `qwen3.5:4b`
- Memory extraction model: `mustafa-persona:0.6b`
- Embeddings model: `nomic-embed-text`
- Default context on VPS: `num_ctx 1024`
- Runtime sampling defaults: `temperature=0.35`, `top_p=0.85`, `repeat_penalty=1.03`, `num_predict=180`
- Optional CPU thread cap: `OLLAMA_NUM_THREAD`, set to physical core count by VPS scripts when missing or `0`
- Thinking disabled in API calls: `think=false`
- Vector DB: ChromaDB in `/app/data/chroma`
- Bot database: SQLite in `/app/data/whoamai-bot.db`

To try the smarter but heavier 2B model on the VPS:

```bash
chmod +x deploy/switch-to-medium-model.sh
./deploy/switch-to-medium-model.sh
```

To return to the lighter model:

```bash
chmod +x deploy/switch-to-light-model.sh
./deploy/switch-to-light-model.sh
```

To try the higher-quality 4B model if the VPS has enough headroom:

```bash
chmod +x deploy/switch-to-4b-model.sh
./deploy/switch-to-4b-model.sh
```

## Memory Architecture

- Core prompt is static and small: professional persona rules, anti-humanization constraints, Suheyla rules, and few-shot WhatsApp examples.
- Dynamic state is injected on every message: current date/time, mood, and whether the current sender is treated as Suheyla.
- Markdown knowledge is chunked into ChromaDB and retrieved only when semantically relevant.
- New long-term facts from WhatsApp chats can be extracted in the background and inserted into the same Chroma collection with `scope=chat_memory`.
- `OWNER_WA_IDS` marks Mustafa's own WhatsApp IDs. Explicit owner messages like `unutma`, `aklinda tut`, `not al`, `hatirla`, or `kaydet` are stored as global Mustafa memory.
- Owner messages can store dated plans and taught response rules, for example `Ben "Naber?" sorusuna "iyi kanka" diye cevap veririm, unutma`.
- Persona Markdown chunks use `scope=persona`; private chat memories are retrieved only for the hashed WhatsApp sender.
- Global owner memories use `visibility=global` and can be retrieved by other active chats when directly relevant.
- Temporary plans keep `expires_at_ts`; examples like `30 dakika sonra` or `yarim saat sonra` expire at the stated time.
- Recent user and assistant messages are kept in SQLite and sent as short conversation history.
- WhatsApp stays as the only user interface.

## Important Files

- `app/app/main.py`: WhatsApp webhook, session handling, history, memory extraction, and Ollama chat bridge.
- `app/app/prompt.py`: core system prompt, dynamic state, and memory extraction prompt.
- `app/app/rag.py`: ChromaDB indexing, retrieval, and chat memory storage.
- `knowledge/mustafa_persona.md`: persona knowledge generated from CSV-style source data.
- `scripts/load_knowledge_to_chroma.py`: manual ChromaDB reindex helper.
- `scripts/generate_persona_knowledge.py`: generate persona Markdown from CSV.
- `deploy/Modelfile.mustafa-persona-light`: `mustafa-persona:0.6b` model definition.
- `deploy/Modelfile.mustafa-persona-medium`: `mustafa-persona:2b` model definition.
- `deploy/Modelfile.mustafa-persona`: `mustafa-persona:4b` model definition.
- `deploy/Modelfile.mustafa-persona-fallback`: older 2B fallback model definition.
- `deploy/docker-compose.local.yml`: local Docker Desktop stack.
- `deploy/docker-compose.yml`: VPS stack.
- `.env.example`: required WhatsApp, Ollama, RAG, and memory settings.

## How WhatsApp Flow Works

1. A WhatsApp user sends: `hey mustafa, baslat`. The Turkish spelling with special characters is also accepted by text folding.
2. The bot activates that sender's session, clears previous short history, and starts in normal mode.
3. Later text messages from the same WhatsApp number are sent to Ollama.
4. The bot builds a system prompt with current Istanbul time, mood, Suheyla mode, and relevant ChromaDB snippets.
5. The bot sends only the recent user history plus the current message to Ollama, then cleans unsafe or repetitive reply fragments.
6. The reply is sent back through Meta WhatsApp Cloud API.
7. If the sender is in `OWNER_WA_IDS` and explicitly says to remember something, the bot stores it immediately as global Mustafa memory and replies with a short acknowledgement.
8. Otherwise, a background task tries to extract new durable private memories from the user message and stores useful ones in ChromaDB.
9. The user can stop with `durdur`, `bitir`, or `kapat`.

Notes:

- Non-text WhatsApp messages receive a short text-only warning.
- Duplicate WhatsApp message IDs are ignored through the `processed_messages` table.
- If a user says `ben Suheyla`, the session switches to Suheyla mode. Saying `ben Mustafa` or `Suheyla degilim` turns that mode off.

## Required Meta WhatsApp Values

Create `.env` from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Fill these values:

```env
WHATSAPP_VERIFY_TOKEN=choose-a-random-secret
WHATSAPP_ACCESS_TOKEN=your-meta-access-token
WHATSAPP_PHONE_NUMBER_ID=your-whatsapp-phone-number-id
```

Meta webhook callback URL:

```text
https://YOUR_DOMAIN/webhook/whatsapp
```

Use the same `WHATSAPP_VERIFY_TOKEN` in Meta's webhook verification screen. Subscribe the WhatsApp app webhook to message events.

## Main Environment Settings

The defaults in `.env.example` are:

```env
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=mustafa-persona:0.6b
OLLAMA_NUM_CTX=1024
OLLAMA_THINK=false
OLLAMA_TEMPERATURE=0.35
OLLAMA_TOP_P=0.85
OLLAMA_REPEAT_PENALTY=1.03
OLLAMA_NUM_PREDICT=180
OLLAMA_NUM_THREAD=0
PERSONA_KNOWLEDGE_PATH=/app/knowledge/mustafa_persona.md
CHROMA_PATH=/app/data/chroma
CHROMA_COLLECTION=mustafa_persona
EMBEDDING_MODEL=nomic-embed-text
RAG_TOP_K=2
RAG_MAX_CONTEXT_CHARS=800
RAG_MIN_SCORE=0.35
MEMORY_EXTRACTION_ENABLED=true
MEMORY_EXTRACTION_MODEL=mustafa-persona:0.6b
MEMORY_EXTRACTION_NUM_CTX=512
MEMORY_MAX_CHARS=240
BOT_DATABASE_PATH=/app/data/whoamai-bot.db
ACTIVATION_PHRASE=hey mustafa, baslat
STOP_PHRASES=durdur,bitir,kapat
OWNER_WA_IDS=
MAX_HISTORY_MESSAGES=6
PROCESSED_MESSAGE_RETENTION_DAYS=7
```

Set `OWNER_WA_IDS` to comma-separated WhatsApp numeric IDs, for example `905xxxxxxxxx,905yyyyyyyyy`. Do not commit real phone numbers. This value is required for global learning, so only your own numbers can create global memory.

## Local Docker Test

Docker Desktop must be running.

```powershell
powershell -ExecutionPolicy Bypass -File deploy/bootstrap-local-docker.ps1
```

This starts:

- `whoamai-ollama`
- `whoamai-whatsapp-bot`

Local endpoints:

```text
Bot health: http://localhost:8000/health
Ollama API: http://localhost:11435
```

The local bootstrap creates the lightweight persona model and also creates the local 4B and 2B persona models from their Modelfiles. If local RAG indexing logs show that the embedding model is missing, pull it once:

```powershell
docker exec whoamai-ollama ollama pull nomic-embed-text
docker restart whoamai-whatsapp-bot
```

Local WhatsApp webhook testing needs a public HTTPS tunnel, for example Cloudflare Tunnel or ngrok:

```text
https://YOUR-TUNNEL-DOMAIN/webhook/whatsapp
```

To start a no-domain temporary Cloudflare Tunnel with Docker:

```powershell
docker compose -f deploy/docker-compose.local.yml -f deploy/docker-compose.tunnel.yml up -d
powershell -ExecutionPolicy Bypass -File deploy/show-tunnel-url.ps1
```

Use the printed URL plus `/webhook/whatsapp` as the Meta callback URL.
The free TryCloudflare URL can change after restarts, so it is suitable for testing, not stable production.

## VPS Install

On the VPS:

```bash
git clone YOUR_GITHUB_REPO_URL WhoAmAI
cd WhoAmAI
cp .env.example .env
nano .env
chmod +x deploy/install-vps.sh
./deploy/install-vps.sh
```

The script installs Docker and Ollama, pulls `qwen3:0.6b` and `nomic-embed-text`, creates `mustafa-persona:0.6b`, and starts the WhatsApp bot.
It also configures Ollama to listen on `0.0.0.0:11434`, sets runtime model defaults in `.env`, and caps `OLLAMA_NUM_THREAD` to the detected physical CPU core count when the value is missing or `0`.

After install:

```bash
chmod +x deploy/smoke-test.sh
./deploy/smoke-test.sh
```

If `knowledge/mustafa_persona.md` changes, rebuild the Chroma index:

```bash
chmod +x deploy/reindex-knowledge.sh
./deploy/reindex-knowledge.sh
```

## Optional GGUF Model Path

The default deployment keeps the current Ollama/Qwen model path. If a GGUF file is later copied to the VPS, create a separate model without changing the default install:

```bash
cat > deploy/Modelfile.mustafa-persona-gguf <<'EOF'
FROM /opt/models/your-model.Q4_K_M.gguf

PARAMETER num_ctx 1024
PARAMETER temperature 0.35
PARAMETER top_p 0.85
PARAMETER repeat_penalty 1.03
PARAMETER num_predict 180

SYSTEM """
/no_think
Sen Mustafa Salih Ozdal personasisin. Kisa, net, profesyonel ve dogal cevap ver.
Bilmedigin detaylari uydurma; duygusal simulasyon veya abartili insanilestirme yapma.
"""
EOF

ollama create mustafa-persona:gguf -f deploy/Modelfile.mustafa-persona-gguf
```

Then set `OLLAMA_MODEL=mustafa-persona:gguf` in `.env` and restart the bot container.

## HTTPS Requirement

Meta WhatsApp Cloud API requires a public HTTPS webhook URL. A domain is the clean production option, but it is not required for a temporary test. Without a domain, run a Cloudflare Tunnel and use the generated `trycloudflare.com` URL in Meta.

No-domain VPS tunnel:

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.tunnel.yml up -d
chmod +x deploy/show-tunnel-url.sh
./deploy/show-tunnel-url.sh
```

If using a domain later, put a reverse proxy in front of port `8000`.

Example Caddy config:

```text
your-domain.com {
  reverse_proxy 127.0.0.1:8000
}
```

See `deploy/Caddyfile.example`.
