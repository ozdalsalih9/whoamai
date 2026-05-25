#!/usr/bin/env bash
set -euo pipefail

source ./deploy/env-utils.sh

ollama pull qwen3.5:4b
ollama pull nomic-embed-text
ollama create mustafa-persona:4b -f deploy/Modelfile.mustafa-persona

set_env_value OLLAMA_MODEL mustafa-persona:4b
set_env_value OLLAMA_NUM_CTX 2048
set_env_value OLLAMA_THINK false
apply_runtime_env_defaults

docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.tunnel.yml up -d --build

echo "Switched to mustafa-persona:4b with num_ctx=2048 and repeat_penalty=1.03."
