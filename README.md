# Mustafa Persona WhatsApp Bot MVP

This project runs a personal Mustafa persona bot over WhatsApp using:

- Ollama for local LLM inference
- Meta WhatsApp Cloud API for WhatsApp messages
- A small FastAPI webhook service
- Persona prompt plus `knowledge/mustafa_persona.md`

Open WebUI is no longer required for the main flow. If `localhost:3000` shows an Open WebUI admin screen, that is from the earlier UI approach and can be ignored for the WhatsApp bot.

## Current Model Defaults

- Default model on shared 4 vCPU VPS: `mustafa-persona:0.6b`
- Higher-quality model: `mustafa-persona:4b`
- Medium fallback model: `mustafa-persona:2b`
- Base model: `qwen3.5:4b`
- Fallback model: `mustafa-persona:2b`
- Fallback base: `qwen3.5:2b`
- Embeddings model kept available: `nomic-embed-text`
- Context on VPS: `num_ctx 1024`

## Important Files

- `app/app/main.py`: WhatsApp webhook and Ollama chat bridge.
- `knowledge/mustafa_persona.md`: persona knowledge generated from the CSV.
- `deploy/Modelfile.mustafa-persona`: primary Ollama persona model.
- `deploy/Modelfile.mustafa-persona-fallback`: fallback Ollama persona model.
- `deploy/docker-compose.local.yml`: local Docker Desktop stack.
- `deploy/docker-compose.yml`: VPS stack.
- `.env.example`: required WhatsApp/Ollama settings.

## How WhatsApp Flow Works

1. A WhatsApp user sends: `hey mustafa, başlat`
2. The bot activates that sender's session.
3. Later messages from the same WhatsApp number are sent to Ollama.
4. Ollama receives the persona system prompt plus `knowledge/mustafa_persona.md`.
5. The bot replies back to WhatsApp through Meta Cloud API.
6. The user can stop with `durdur`, `bitir`, or `kapat`.

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

The script installs Docker and Ollama, pulls the models, creates the persona models, and starts the WhatsApp bot.

After install:

```bash
chmod +x deploy/smoke-test.sh
./deploy/smoke-test.sh
```

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
