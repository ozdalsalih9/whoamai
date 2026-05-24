#!/usr/bin/env bash

set_env_value() {
  local key="$1"
  local value="$2"

  python3 - "$key" "$value" <<'PY'
import sys
from pathlib import Path

key, value = sys.argv[1], sys.argv[2]
path = Path(".env")
lines = path.read_text().splitlines() if path.exists() else []
prefix = f"{key}="
updated = False

for index, line in enumerate(lines):
    if line.startswith(prefix):
        lines[index] = f"{key}={value}"
        updated = True
        break

if not updated:
    lines.append(f"{key}={value}")

path.write_text("\n".join(lines) + "\n")
PY
}

set_env_default() {
  local key="$1"
  local value="$2"

  if [ ! -f .env ] || ! grep -q "^${key}=" .env; then
    set_env_value "$key" "$value"
  fi
}

set_env_positive_default() {
  local key="$1"
  local value="$2"
  local current=""

  if [ -f .env ]; then
    current="$(grep "^${key}=" .env | tail -n 1 | cut -d= -f2- || true)"
  fi

  if [ -z "$current" ] || [ "$current" = "0" ]; then
    set_env_value "$key" "$value"
  fi
}

physical_core_count() {
  local cores=""

  if command -v lscpu >/dev/null 2>&1; then
    cores="$(lscpu -p=Core,Socket 2>/dev/null | grep -v '^#' | sort -u | wc -l | tr -d ' ')"
  fi

  if [ -z "$cores" ] || [ "$cores" = "0" ]; then
    cores="$(nproc 2>/dev/null || echo 1)"
  fi

  echo "$cores"
}

apply_runtime_env_defaults() {
  set_env_default OLLAMA_TEMPERATURE 0.35
  set_env_default OLLAMA_TOP_P 0.85
  set_env_default OLLAMA_REPEAT_PENALTY 1.03
  set_env_default OLLAMA_NUM_PREDICT 180
  set_env_positive_default OLLAMA_NUM_THREAD "$(physical_core_count)"
  set_env_default MAX_HISTORY_MESSAGES 6
  set_env_default PROCESSED_MESSAGE_RETENTION_DAYS 7
}
