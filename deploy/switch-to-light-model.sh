#!/usr/bin/env bash
set -euo pipefail

ollama pull qwen3:0.6b
ollama create mustafa-persona:0.6b -f deploy/Modelfile.mustafa-persona-light

python3 - <<'PY'
from pathlib import Path

path = Path(".env")
text = path.read_text()
replacements = {
    "OLLAMA_MODEL=": "OLLAMA_MODEL=mustafa-persona:0.6b",
    "OLLAMA_NUM_CTX=": "OLLAMA_NUM_CTX=1024",
    "PERSONA_MAX_CHARS=": "PERSONA_MAX_CHARS=2500",
    "OLLAMA_THINK=": "OLLAMA_THINK=false",
}

lines = text.splitlines()
seen = set()
for i, line in enumerate(lines):
    for prefix, value in replacements.items():
        if line.startswith(prefix):
            lines[i] = value
            seen.add(prefix)

for prefix, value in replacements.items():
    if prefix not in seen:
        lines.append(value)

path.write_text("\n".join(lines) + "\n")
PY

docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.tunnel.yml up -d --build

echo "Switched to mustafa-persona:0.6b with num_ctx=1024."
