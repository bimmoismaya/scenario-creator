#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
exec .venv/bin/uvicorn --factory app.server:create_app --host 0.0.0.0 --port 8000
