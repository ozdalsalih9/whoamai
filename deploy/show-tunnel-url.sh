#!/usr/bin/env bash
set -euo pipefail

docker logs whoamai-cloudflared 2>&1 \
  | grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' \
  | tail -n 1
