#!/usr/bin/env bash
set -euo pipefail

echo "Checking Ollama service..."
curl -fsS http://127.0.0.1:11434/api/tags >/dev/null

echo "Checking default lightweight persona model..."
curl --max-time 180 -fsS http://127.0.0.1:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mustafa-persona:2b",
    "stream": false,
    "options": {
      "num_ctx": 2048
    },
    "messages": [
      {
        "role": "user",
        "content": "Sadece OK yaz."
      }
    ]
  }' >/dev/null

echo "Checking embedding model..."
curl -fsS http://127.0.0.1:11434/api/embed \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nomic-embed-text",
    "input": "Mustafa persona bilgi tabani testi"
  }' >/dev/null

echo "Checking WhatsApp bot container..."
docker ps --filter "name=whoamai-whatsapp-bot" --filter "status=running" --format "{{.Names}}" | grep -q '^whoamai-whatsapp-bot$'

echo "Checking WhatsApp bot health endpoint..."
curl -fsS http://127.0.0.1:8000/health >/dev/null

echo "Checking WhatsApp bot can reach Ollama through Docker host gateway..."
docker exec whoamai-whatsapp-bot python - <<'PY'
import os
import httpx

base_url = os.environ.get("OLLAMA_BASE_URL", "http://172.17.0.1:11434")
response = httpx.get(f"{base_url}/api/tags", timeout=10)
response.raise_for_status()
print(response.json())
PY

echo "Smoke test passed."
