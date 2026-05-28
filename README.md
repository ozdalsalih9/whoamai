# Mustafa Persona Telegram Bot MVP

This project runs a personal Mustafa persona bot over Telegram using:

- Ollama for local LLM inference
- Telegram Bot API for message transport
- A small FastAPI service for health checks and optional Telegram webhook delivery
- ChromaDB RAG over `knowledge/mustafa_persona.md`
- SQLite for Telegram session state, short chat history, and processed update IDs

The main Telegram flow uses long polling by default, so a public HTTPS webhook URL is not required. Open WebUI is not part of the bot flow.

## Security Note

A Telegram bot token was pasted during setup. Treat that token as exposed.

Do this in BotFather before deploying:

1. Revoke the old token.
2. Generate a fresh token.
3. Put the fresh token only in `.env` as `TELEGRAM_BOT_TOKEN=...`.
4. Do not commit `.env` or paste the new token into chat, README, logs, or issues.

## Current Project Status

Implemented so far:

- Telegram Bot API integration with long polling.
- Optional Telegram webhook receiver at `/webhook/telegram`.
- Health endpoint at `/health`.
- `/start` activation flow plus the old `hey mustafa, baslat` activation phrase.
- `/stop`, `durdur`, `bitir`, and `kapat` stop flow.
- Per-chat session state in SQLite, including active/inactive state and Suheyla mode.
- Short rolling message history with configurable retention count.
- Duplicate Telegram update protection through persisted processed IDs.
- Text-only handling with a warning for non-text Telegram messages.
- Ollama chat integration with `/api/chat`, `think=false`, runtime sampling options, and optional CPU thread cap.
- Local RAG over `knowledge/mustafa_persona.md` using ChromaDB and `nomic-embed-text`.
- Private per-user chat memory extraction from Telegram messages.
- Owner-only global Mustafa memory through `OWNER_TELEGRAM_IDS`.
- Expiring global plan memory for phrases like `30 dakika sonra`, `bugun saat 17:30`, `yarin`, weekdays, `bu hafta`, `haftaya`, and `ay sonu`.
- Learned response-rule memory, for example `Ben "Naber?" sorusuna "iyi kanka" diye cevap veririm, unutma`.
- Learned relationship memory, for example `Eren benim arkadasim, unutma`.
- Deterministic guardrail replies for common messages such as `Naber?`, praise messages, profile facts, self-introduction, and plan queries.
- Reply cleanup that removes repeated sentences, classic AI helper closers, off-topic Suheyla references, and banned humanization/assistant fragments.
- Local Docker bootstrap for Windows.
- VPS install scripts, smoke tests, Chroma reindex helper, model switching scripts, and optional Cloudflare Tunnel support for webhook mode.
- GitHub Actions deploy to VPS over SSH on push to `main` or manual workflow dispatch.
- Pytest coverage for memory scoping, persona reset, global plans, expiry cleanup, deterministic replies, profile answers, learned response rules, and reply cleanup.

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
- 4B context when switched through script: `num_ctx 2048`
- Runtime sampling defaults: `temperature=0.35`, `top_p=0.85`, `repeat_penalty=1.03`, `num_predict=180`
- Optional CPU thread cap: `OLLAMA_NUM_THREAD`, set to physical core count by VPS scripts when missing or `0`
- Ollama model residency: `OLLAMA_KEEP_ALIVE=30m`
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

- Core prompt is static and small: professional persona rules, anti-humanization constraints, Suheyla rules, and few-shot Telegram examples.
- Dynamic state is injected on every message: current date/time, mood, and whether the current sender is treated as Suheyla.
- Markdown knowledge is chunked into ChromaDB and retrieved only when semantically relevant.
- New long-term facts from Telegram chats can be extracted in the background and inserted into the same Chroma collection with `scope=chat_memory`.
- `OWNER_TELEGRAM_IDS` marks Mustafa's own Telegram user/chat IDs. Explicit owner messages like `unutma`, `aklinda tut`, `not al`, `hatirla`, or `kaydet` are stored as global Mustafa memory.
- Owner messages can store dated plans and taught response rules, for example `Ben "Naber?" sorusuna "iyi kanka" diye cevap veririm, unutma`.
- Owner messages can store relationships, for example `Eren benim arkadasim, unutma`; later `Ben Eren` receives a friend-tone deterministic reply.
- Persona Markdown chunks use `scope=persona`; private chat memories are retrieved only for the hashed Telegram chat/user.
- Global owner memories use `visibility=global` and can be retrieved by other active chats when directly relevant.
- Temporary plans keep `expires_at_ts`; examples like `30 dakika sonra` or `yarim saat sonra` expire at the stated time.
- Expired chat memories are cleaned periodically instead of on every message.
- RAG retrieval reuses a single query embedding across persona, global memory, and private chat memory lookups.
- Recent user and assistant messages are kept in SQLite and sent as short conversation history.
- Deterministic answer paths run before the LLM for simple status, praise, profile, self-intro, plan, and learned response-rule questions.

## Important Files

- `app/app/main.py`: Telegram polling/webhook handling, session handling, history, memory extraction, and Ollama chat bridge.
- `app/app/prompt.py`: core system prompt, dynamic state, and memory extraction prompt.
- `app/app/rag.py`: ChromaDB indexing, retrieval, and chat memory storage.
- `knowledge/mustafa_persona.md`: persona knowledge generated from CSV-style source data.
- `scripts/load_knowledge_to_chroma.py`: manual ChromaDB reindex helper.
- `scripts/generate_persona_knowledge.py`: generate persona Markdown from CSV.
- `deploy/Modelfile.mustafa-persona-light`: `mustafa-persona:0.6b` model definition.
- `deploy/Modelfile.mustafa-persona-medium`: `mustafa-persona:2b` model definition.
- `deploy/Modelfile.mustafa-persona`: `mustafa-persona:4b` model definition.
- `deploy/Modelfile.mustafa-persona-fallback`: older 2B fallback model definition.
- `deploy/env-utils.sh`: shared deploy helpers for `.env` mutation and CPU thread defaults.
- `deploy/configure-ollama-host.sh`: configures Ollama host binding for Docker access on VPS.
- `deploy/docker-compose.local.yml`: local Docker Desktop stack.
- `deploy/docker-compose.yml`: VPS stack.
- `deploy/docker-compose.tunnel.yml`: optional Cloudflare Tunnel sidecar for webhook mode.
- `.github/workflows/deploy-vps.yml`: SSH-based VPS deployment workflow.
- `.env.example`: required Telegram, Ollama, RAG, and memory settings.

## Telegram Flow

1. A Telegram user sends `/start`. The old `hey mustafa, baslat` phrase also works.
2. The bot activates that chat, clears previous short history, and starts in normal mode.
3. Later text messages from the same Telegram chat are processed by the bot.
4. The bot builds a system prompt with current Istanbul time, mood, Suheyla mode, and relevant ChromaDB snippets.
5. Before calling the LLM, deterministic handlers answer simple status, praise, profile, self-intro, plan, and learned response-rule messages.
6. If no deterministic answer exists, the bot sends recent history plus the current message to Ollama, then cleans unsafe or repetitive reply fragments.
7. The reply is sent back through Telegram Bot API.
8. If the sender is in `OWNER_TELEGRAM_IDS` and explicitly says to remember something, the bot stores it immediately as global Mustafa memory and replies with a short acknowledgement.
9. Otherwise, a background task tries to extract new durable private memories from the user message and stores useful ones in ChromaDB.
10. The user can stop with `/stop`, `durdur`, `bitir`, or `kapat`.

Notes:

- Non-text Telegram messages receive a short text-only warning.
- Duplicate Telegram update IDs are ignored through the `processed_messages` table.
- If a user says `ben Suheyla`, the session switches to Suheyla mode. Saying `ben Mustafa` or `Suheyla degilim` turns that mode off.
- Inactive users are prompted to send `/start`.
- Explicit memory commands from non-owner senders are rejected instead of being stored globally.

## Deterministic Replies and Rules

Some replies intentionally bypass the LLM:

- Basic status messages like `Naber?` return `iyi kanka yuvarlanip gidioz`.
- Short praise messages return a compact acknowledgement such as `eyw` or `sagol`.
- Profile questions such as age, height, university, city, name, football team, NBA player, and eye color read from `knowledge/mustafa_persona.md`.
- Self-introduction requests are assembled from known persona facts.
- Plan questions use active global plan memory when there is a matching plan, otherwise they return the no-plan fallback.
- Owner-taught response rules override the defaults when the normalized question matches.
- If someone identifies as a learned friend, for example `Ben Eren`, the bot replies with a short friend-tone response such as `naber kanka`.

## Required Telegram Values

Create `.env` from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Fill this value with a fresh BotFather token:

```env
TELEGRAM_BOT_TOKEN=your-fresh-botfather-token
```

Set `OWNER_TELEGRAM_IDS` to comma-separated numeric Telegram chat/user IDs for accounts allowed to create global memory:

```env
OWNER_TELEGRAM_IDS=123456789,987654321
```

Do not commit real tokens or personal IDs.

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
OLLAMA_KEEP_ALIVE=30m
PERSONA_KNOWLEDGE_PATH=/app/knowledge/mustafa_persona.md
CHROMA_PATH=/app/data/chroma
CHROMA_COLLECTION=mustafa_persona
EMBEDDING_MODEL=nomic-embed-text
RAG_TOP_K=2
RAG_MAX_CONTEXT_CHARS=800
RAG_MIN_SCORE=0.35
MEMORY_CLEANUP_INTERVAL_SECONDS=300
MEMORY_EXTRACTION_ENABLED=true
MEMORY_EXTRACTION_MODEL=mustafa-persona:0.6b
MEMORY_EXTRACTION_NUM_CTX=512
MEMORY_MAX_CHARS=240
TELEGRAM_BOT_TOKEN=change-this-telegram-bot-token
TELEGRAM_POLLING_ENABLED=true
TELEGRAM_POLL_INTERVAL_SECONDS=1
TELEGRAM_REQUEST_TIMEOUT=50
BOT_DATABASE_PATH=/app/data/whoamai-bot.db
ACTIVATION_PHRASE=hey mustafa, baslat
STOP_PHRASES=/stop,durdur,bitir,kapat
OWNER_TELEGRAM_IDS=
MAX_HISTORY_MESSAGES=6
PROCESSED_MESSAGE_RETENTION_DAYS=7
```

## Local Docker Test

Docker Desktop must be running.

```powershell
powershell -ExecutionPolicy Bypass -File deploy/bootstrap-local-docker.ps1
```

This starts:

- `whoamai-ollama`
- `whoamai-telegram-bot`

Local endpoints:

```text
Bot health: http://localhost:8000/health
Ollama API: http://localhost:11435
```

The local bootstrap creates the lightweight persona model and also creates the local 4B and 2B persona models from their Modelfiles. If local RAG indexing logs show that the embedding model is missing, pull it once:

```powershell
docker exec whoamai-ollama ollama pull nomic-embed-text
docker restart whoamai-telegram-bot
```

With `TELEGRAM_POLLING_ENABLED=true`, the bot starts receiving Telegram messages without a public tunnel.

## Optional Telegram Webhook Mode

Long polling is the default and is simpler for VPS usage. If you later want webhook mode:

1. Set `TELEGRAM_POLLING_ENABLED=false`.
2. Expose the FastAPI service through HTTPS.
3. Configure Telegram `setWebhook` to:

```text
https://YOUR_DOMAIN/webhook/telegram
```

For a temporary no-domain tunnel:

```powershell
docker compose -f deploy/docker-compose.local.yml -f deploy/docker-compose.tunnel.yml up -d
powershell -ExecutionPolicy Bypass -File deploy/show-tunnel-url.ps1
```

Use the printed URL plus `/webhook/telegram` as the Telegram webhook URL.

## Local Python Tests

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest
```

The tests set dummy Telegram environment values through `tests/conftest.py`, so a real Telegram token is not needed for unit tests.

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

The script installs Docker and Ollama, pulls `qwen3:0.6b` and `nomic-embed-text`, creates `mustafa-persona:0.6b`, removes the legacy `whoamai-whatsapp-bot` container if present, and starts the Telegram bot.
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

## GitHub Actions VPS Deploy

The repo includes `.github/workflows/deploy-vps.yml`. On every push to `main`, GitHub Actions can SSH into the VPS, pull the latest commit, rebuild the Docker bot, reindex Chroma knowledge, and run a health check.

Required GitHub repository secrets:

```text
VPS_HOST=your-vps-ip-or-domain
VPS_USER=root
VPS_SSH_KEY=private SSH key with access to the VPS
```

Optional GitHub repository secrets or variables:

```text
VPS_PORT=22
VPS_APP_DIR=/root/whoamai
VPS_USE_TUNNEL=true
```

`VPS_APP_DIR` defaults to `$HOME/whoamai` if empty. `VPS_USE_TUNNEL=true` is only needed if you intentionally run webhook mode through `deploy/docker-compose.tunnel.yml`.

Recommended setup:

```bash
ssh-keygen -t ed25519 -C "github-actions-whoamai" -f ~/.ssh/whoamai_github_actions
cat ~/.ssh/whoamai_github_actions.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/whoamai_github_actions
```

Paste the private key output into `VPS_SSH_KEY`. Keep `.env` only on the VPS; do not commit real tokens or personal IDs.

The deploy uses `git pull --ff-only`, so it will fail instead of overwriting tracked edits made directly on the VPS. If deploy fails because of local VPS edits, either commit/stash them on the VPS or reset intentionally after reviewing them.

When the Telegram token changes, update only the VPS `.env`:

```bash
cd ~/whoamai
nano .env
docker compose -f deploy/docker-compose.yml up -d --build
```

## Operational Notes

- Keep `.env` on the machine running the bot.
- `OWNER_TELEGRAM_IDS` should contain only trusted Telegram numeric IDs, because those IDs can create global memory.
- Local Docker uses an Ollama container at `http://ollama:11434` and exposes it on host port `11435`.
- VPS Docker uses the host Ollama service through `http://172.17.0.1:11434`.
- `deploy/reindex-knowledge.sh` is for VPS layout and uses the host Ollama address from inside the bot container.
- Model switch scripts recreate the selected Ollama model, update `.env`, apply runtime defaults, remove the legacy WhatsApp container if present, and restart Docker Compose.
- Long polling does not need a domain, reverse proxy, Cloudflare Tunnel, ngrok, or Telegram webhook registration.

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
