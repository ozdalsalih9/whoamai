#!/usr/bin/env bash
set -euo pipefail

source ./deploy/env-utils.sh

if ! command -v curl >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y curl
fi

if ! command -v python3 >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y python3
fi

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
fi

if ! docker compose version >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y docker-compose-plugin
fi

if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

sudo systemctl enable ollama
sudo systemctl start ollama
./deploy/configure-ollama-host.sh

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "Edit .env and fill TELEGRAM_BOT_TOKEN, then rerun this script."
  exit 1
fi

if grep -q "change-this-" .env; then
  echo ".env still contains placeholder values. Edit .env before starting the bot."
  exit 1
fi

if ! grep -q "^TELEGRAM_BOT_TOKEN=.\+" .env; then
  echo "TELEGRAM_BOT_TOKEN is missing in .env. Add a fresh token from BotFather, then rerun this script."
  exit 1
fi

apply_runtime_env_defaults

ollama pull qwen3:0.6b
ollama pull nomic-embed-text

ollama create mustafa-persona:0.6b -f deploy/Modelfile.mustafa-persona-light

docker rm -f whoamai-whatsapp-bot >/dev/null 2>&1 || true
docker compose -f deploy/docker-compose.yml up -d

echo "Telegram bot health: http://SERVER_IP:8000/health"
echo "Telegram polling is enabled by default; no public webhook is required."
echo "Default lightweight model: mustafa-persona:0.6b"
