#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
[[ -f .env ]] || cp .env.example .env
[[ -f frontend/.env ]] || cp frontend/.env.example frontend/.env

(cd backend && uv sync --locked --python 3.11 && uv run --locked alembic upgrade head)
npm --prefix frontend ci
