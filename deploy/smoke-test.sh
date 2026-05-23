#!/usr/bin/env bash
set -euo pipefail

echo "Checking Ollama service..."
curl -fsS http://127.0.0.1:11434/api/tags >/dev/null

echo "Checking primary persona model..."
curl -fsS http://127.0.0.1:11434/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mustafa-persona:4b",
    "stream": false,
    "messages": [
      {
        "role": "user",
        "content": "Mustafa kimdir? Kisa ve temkinli cevap ver."
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

echo "Smoke test passed."
