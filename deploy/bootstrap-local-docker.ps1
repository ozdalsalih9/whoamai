$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
    Write-Host "Fill TELEGRAM_BOT_TOKEN before connecting Telegram."
}

docker rm -f whoamai-whatsapp-bot 2>$null
docker compose -f deploy/docker-compose.local.yml up -d

docker exec whoamai-ollama ollama pull qwen3:0.6b

docker cp deploy/Modelfile.mustafa-persona-light whoamai-ollama:/tmp/Modelfile.mustafa-persona-light
docker cp deploy/Modelfile.mustafa-persona whoamai-ollama:/tmp/Modelfile.mustafa-persona
docker cp deploy/Modelfile.mustafa-persona-medium whoamai-ollama:/tmp/Modelfile.mustafa-persona-medium

docker exec whoamai-ollama ollama create mustafa-persona:0.6b -f /tmp/Modelfile.mustafa-persona-light
docker exec whoamai-ollama ollama create mustafa-persona:4b -f /tmp/Modelfile.mustafa-persona
docker exec whoamai-ollama ollama create mustafa-persona:2b -f /tmp/Modelfile.mustafa-persona-medium

Write-Host "Ollama API for this project: http://localhost:11435"
Write-Host "Telegram bot health: http://localhost:8000/health"
Write-Host "Default lightweight model: mustafa-persona:0.6b"
