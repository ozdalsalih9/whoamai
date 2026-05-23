$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
    Write-Host "Fill WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_VERIFY_TOKEN before connecting Meta webhooks."
}

docker compose -f deploy/docker-compose.local.yml up -d

docker exec whoamai-ollama ollama pull qwen3:0.6b

docker cp deploy/Modelfile.mustafa-persona-light whoamai-ollama:/tmp/Modelfile.mustafa-persona-light
docker cp deploy/Modelfile.mustafa-persona whoamai-ollama:/tmp/Modelfile.mustafa-persona
docker cp deploy/Modelfile.mustafa-persona-fallback whoamai-ollama:/tmp/Modelfile.mustafa-persona-fallback

docker exec whoamai-ollama ollama create mustafa-persona:0.6b -f /tmp/Modelfile.mustafa-persona-light
docker exec whoamai-ollama ollama create mustafa-persona:4b -f /tmp/Modelfile.mustafa-persona
docker exec whoamai-ollama ollama create mustafa-persona:2b -f /tmp/Modelfile.mustafa-persona-fallback

Write-Host "Ollama API for this project: http://localhost:11435"
Write-Host "WhatsApp webhook health: http://localhost:8000/health"
Write-Host "Default lightweight model: mustafa-persona:0.6b"
