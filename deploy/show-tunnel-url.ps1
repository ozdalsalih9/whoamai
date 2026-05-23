$ErrorActionPreference = "Stop"

docker logs whoamai-cloudflared 2>&1 |
  Select-String -Pattern "https://[-a-z0-9]+\.trycloudflare\.com" |
  Select-Object -Last 1 |
  ForEach-Object { $_.Matches.Value }
