# DefectVision Pro

An industrial visual quality-inspection project for Bottle, Metal Nut, and Tile. The workspace is backed by FastAPI and SQLite for inspection history, model status, analytics, and PDF reports. Inference requires a trained checkpoint and adapter.

## Prerequisites

Use Git, Node.js 24 LTS with npm, Python 3.11, and uv. The foundation was verified on Apple Silicon macOS with Node 24.14.1, npm 11.11.0, Python 3.11.15, and uv 0.13.5. Frontend and backend dependencies are locked in `frontend/package-lock.json` and `backend/uv.lock`.

## macOS

Run from the project root.

```bash
bash scripts/setup.sh
```

Backend terminal:

```bash
cd backend
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend terminal:

```bash
npm --prefix frontend run dev -- --host 127.0.0.1
```

## Windows PowerShell

Install the Windows distributions of Node.js 24, Python 3.11, Git, and uv. Run from the project root.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

In a backend terminal, run `Set-Location backend` and the same uvicorn command as above. In a frontend terminal at the project root, run `npm.cmd --prefix frontend run dev -- --host 127.0.0.1`.

Open [the dashboard](http://127.0.0.1:5173), [the API docs](http://127.0.0.1:8000/docs), or [the health endpoint](http://127.0.0.1:8000/api/v1/health).

## Configuration

- Root `.env` sets `DV_CORS_ORIGINS` as a JSON list and optionally `DV_DATABASE_PATH`. Relative database paths resolve from the project root.
- Root `.env` also sets optional image storage, upload size, pixel, and batch limits. See [the API contract](docs/frontend-api.md) for routes and inference behavior.
- `frontend/.env` sets `VITE_API_BASE_URL`. Restart Vite after changing this file.
- If SQLite is unavailable, run `uv run --locked alembic upgrade head` from `backend/` and refresh the status page.

## Checks

```bash
npm --prefix frontend test
npm --prefix frontend run build
cd backend
uv run --locked python -c "from app.main import app; print(app.title)"
uv run --locked alembic check
uv run --locked pytest -q
```

## Project layout and PatchCore

`frontend/` holds the React workspace. `backend/` holds the FastAPI service, migrations, and tests. `ml/` is for training and evaluation. `datasets/`, `models/`, and `storage/` reserve local artifact locations. `scripts/` contains setup entry points, and `docs/` explains the architecture.

See the [PatchCore guide](ml/README.md) to obtain MVTec AD, validate the official splits, train and evaluate each category, and launch the API with calibrated checkpoints.
