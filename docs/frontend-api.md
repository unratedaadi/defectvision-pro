# DefectVision Pro API

FastAPI publishes the interactive reference at `/docs` and its OpenAPI schema at `/openapi.json`. The frontend uses this schema to discover available features. The original `/api/v1/health` remains compatible.

| Method and path | Request and response |
| --- | --- |
| GET `/api/health` | SQLite and product catalog status |
| GET `/api/models` | Latest registry entry and readiness per category |
| POST `/api/inspect` | Multipart `file`, `category`, optional `source` (`upload` or `webcam`); 201 with the saved inspection |
| POST `/api/inspect/batch` | Multipart repeated `files` and `category`. Returns 202 and a job URL in `Location`. A second active batch returns 429. |
| GET `/api/inspect/batch/{id}` | Persisted job status, progress counts, stored results, and indexed failures |
| POST `/api/inspect/webcam` | Multipart `file` and `category`. Returns a temporary frame ID, prediction, and inline image layers. |
| POST `/api/inspect/webcam/{id}/save` | Saves the existing frame and returns the stored inspection. Retrying a saved ID returns the same record. |
| GET `/api/inspections` | `search` matches ID or filename. Also accepts `category`, `prediction`, inclusive UTC `dateFrom` and `dateTo` (YYYY-MM-DD), `sort` (`newest` or `oldest`), `page` (1-based), and `pageSize` (1–100). Returns `{items, total}`. |
| GET / DELETE `/api/inspections/{id}` | Inspection record / 204 after deletion |
| GET `/api/inspections/{id}/media/{kind}` | PNG for `original`, `heatmap`, `overlay`, or a thumbnail up to 120 × 120 |
| GET `/api/analytics/summary` | Counts, defect percentages, and measured latency for `days` (1–365) and optional `category` |
| GET `/api/analytics/trends` | Daily UTC counts and defect percentages for the same filters |
| GET `/api/analytics/dashboard` | Summary, daily trends, UTC bounds, and up to five matching recent inspections from one SQLite snapshot |
| GET `/api/evaluation/{category}` | Recorded metrics and evaluation provenance, including ROC points and available localization samples. Returns 404 if absent. |
| GET `/api/evaluation/{category}/samples/{index}` | PNG comparison of original, anomaly overlay, and ground-truth mask. Use the sample URL from the evaluation response to request the matching model version and, when available, checksum. |
| GET `/api/reports/{id}` | Downloadable PDF for a saved inspection |
| GET `/api/reports/batch/{id}` | Downloadable batch status, counts, and saved inspection results |
| GET `/api/reports/inspections.pdf` | Downloadable summary PDF for `days` |

The reporting window includes today in UTC. Within a nonempty period, days without inspections have zero counts and a null defect percentage. Defect percentage is defective inspections divided by all inspections in the group, multiplied by 100. Average inference latency uses only saved rows with measured adapter time. Earlier rows with null latency still count toward inspection totals.

Category values are `bottle`, `metal_nut`, and `tile`. Uploaded images are validated by decoded content, re-encoded as metadata-free PNG, and stored under generated names only after inference succeeds. Per-file bytes, decoded pixels, and batch count are configurable via the root environment template. The API also bounds the multipart request size. Use the service on a trusted local network.

With `DV_PATCHCORE_ENABLED=true`, the API registers local calibrated artifacts at startup. Inspection endpoints return HTTP 503 with `detail.code: model_not_ready` when the requested category lacks a usable model. Predictions contain a raw score, category threshold, and image layers. See the [ML setup guide](../ml/README.md).

Run one API process for the local worker. It stages the uploaded files, returns a job ID, and processes one image at a time in a separate thread. Each result or validation failure updates SQLite. Graceful shutdown waits for the active job. After an interruption, startup marks unfinished jobs failed and preserves completed inspections.

The browser samples webcam frames at the chosen interval with one preview request in flight. The API holds at most eight recent previews per process for up to five minutes of save eligibility. Saving persists the original inference result and media. An expired or evicted frame returns `404 frame_expired`.
