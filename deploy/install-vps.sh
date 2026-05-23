#!/usr/bin/env bash
set -euo pipefail

if ! command -v curl >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y curl
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
  echo "Edit .env and fill WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_VERIFY_TOKEN, then rerun this script."
  exit 1
fi

if grep -q "change-this-" .env; then
  echo ".env still contains placeholder WhatsApp values. Edit .env before starting the bot."
  exit 1
fi

ollama pull qwen3:0.6b

ollama create mustafa-persona:0.6b -f deploy/Modelfile.mustafa-persona-light

docker compose -f deploy/docker-compose.yml up -d

echo "WhatsApp bot health: http://SERVER_IP:8000/health"
echo "WhatsApp webhook callback: https://YOUR_DOMAIN/webhook/whatsapp"
echo "Default lightweight model: mustafa-persona:0.6b"
