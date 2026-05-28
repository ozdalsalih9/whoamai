#!/usr/bin/env bash
set -euo pipefail

source ./deploy/env-utils.sh

ollama pull qwen3:0.6b
ollama pull nomic-embed-text
ollama create mustafa-persona:0.6b -f deploy/Modelfile.mustafa-persona-light

set_env_value OLLAMA_MODEL mustafa-persona:0.6b
set_env_value OLLAMA_NUM_CTX 1024
set_env_value OLLAMA_THINK false
apply_runtime_env_defaults

docker rm -f whoamai-whatsapp-bot >/dev/null 2>&1 || true
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.tunnel.yml up -d --build

echo "Switched to mustafa-persona:0.6b with num_ctx=1024 and repeat_penalty=1.03."
