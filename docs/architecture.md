# Foundation architecture

React calls `GET /api/v1/health` through an Axios service. FastAPI checks the required SQLite tables and mapped columns, then reads the product catalog seeded by Alembic. A ready database returns the category list and HTTP 200. A missing migration or other database error returns HTTP 503. Network or browser CORS failures appear as an unreachable API in the frontend.

The backend keeps environment configuration, database access, SQLAlchemy models, API routes, and Pydantic schemas in separate modules. Alembic owns schema changes. The frontend separates route layout, pages, components, hooks, response types, and API calls.

Training, calibration, and evaluation use the same Anomalib PatchCore model and preprocessing as serving. With PatchCore enabled, FastAPI discovers calibrated category artifacts at startup. The inference adapter validates and caches checkpoints, produces scores and image-aligned heatmaps, and hands results to the inspection service for storage in SQLite and on disk. The single-image, batch, and webcam flows use the same inference adapter. History, analytics, and PDF reports read the stored records.
