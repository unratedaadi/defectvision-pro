# Deployment

## GitHub

The repository contains the frontend, backend, training code, tests, and setup documentation. Environment files, datasets, checkpoints, the SQLite database, and uploaded images are Git-ignored. Keep backups of those local artifacts separately.

## Vercel frontend

Import the GitHub repository into Vercel and select `frontend` as the root directory. Use the Vite framework preset, Node.js 24, `npm ci`, `npm run build`, and output directory `dist`. The frontend's `vercel.json` supports direct navigation to React Router pages.

Set `VITE_API_BASE_URL` to the HTTPS address of a reachable FastAPI deployment before building. A build without this variable displays a disconnected-server notice. Local development continues to use `frontend/.env`.

## Inspection backend

The current FastAPI service requires a persistent Python process, SQLite database, image storage, and the trained PatchCore checkpoints. Run it on a persistent host with Python 3.11 and the ML serving environment. Provision HTTPS and access controls appropriate to the audience before exposing stored records to remote users.

Copy each complete category model folder into `models/`, including checkpoint, configuration, calibration, and evaluation metadata. Set `DV_PATCHCORE_ENABLED=true` and an appropriate device, typically `cpu` on a CPU host. Set `DV_CORS_ORIGINS` to a JSON array containing the exact Vercel production origin. Keep database and image directories on persistent storage. Run Alembic migrations before starting the API.

The Vercel frontend deployment does not include the local API process, checkpoint files, inspection database, or uploaded images. Connect the public API address through the Vercel environment variable and redeploy the frontend to enable those features remotely.
