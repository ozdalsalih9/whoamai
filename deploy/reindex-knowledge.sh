#!/usr/bin/env bash
set -euo pipefail

docker exec whoamai-whatsapp-bot python /app/scripts/load_knowledge_to_chroma.py \
  --knowledge /app/knowledge/mustafa_persona.md \
  --chroma-path /app/data/chroma \
  --collection mustafa_persona \
  --ollama-base-url http://172.17.0.1:11434 \
  --embedding-model nomic-embed-text
