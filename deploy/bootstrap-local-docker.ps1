$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
    Write-Host "Fill WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_VERIFY_TOKEN before connecting Meta webhooks."
}

docker compose -f deploy/docker-compose.local.yml up -d

docker exec whoamai-ollama ollama pull qwen3.5:4b
docker exec whoamai-ollama ollama pull qwen3.5:2b
docker exec whoamai-ollama ollama pull nomic-embed-text

docker cp deploy/Modelfile.mustafa-persona whoamai-ollama:/tmp/Modelfile.mustafa-persona
docker cp deploy/Modelfile.mustafa-persona-fallback whoamai-ollama:/tmp/Modelfile.mustafa-persona-fallback

docker exec whoamai-ollama ollama create mustafa-persona:4b -f /tmp/Modelfile.mustafa-persona
docker exec whoamai-ollama ollama create mustafa-persona:2b -f /tmp/Modelfile.mustafa-persona-fallback

Write-Host "Ollama API for this project: http://localhost:11435"
Write-Host "WhatsApp webhook health: http://localhost:8000/health"
Write-Host "Primary model: mustafa-persona:4b"
Write-Host "Fallback model: mustafa-persona:2b"
