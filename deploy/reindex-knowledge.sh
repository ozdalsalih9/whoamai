#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

docker exec whoamai-whatsapp-bot python /app/scripts/load_knowledge_to_chroma.py \
  --knowledge /app/knowledge/mustafa_persona.md \
  --chroma-path /app/data/chroma \
  --collection "${CHROMA_COLLECTION:-mustafa_persona}" \
  --ollama-base-url "${OLLAMA_BASE_URL:-http://172.17.0.1:11434}" \
  --embedding-model "${EMBEDDING_MODEL:-nomic-embed-text}"
