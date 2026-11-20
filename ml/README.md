# Machine learning

Run these commands from the repository root with Python 3.11 and uv. The ML environment pins Anomalib 2.7.0, PyTorch 2.13.0, and torchvision 0.28.0. The lockfile uses CPU wheels on Linux and Windows and standard Apple Silicon wheels on macOS. The runner also detects CUDA if used with a compatible CUDA PyTorch installation.

### Obtain and validate MVTec AD

Download the category data manually from the [official MVTec AD page](https://www.mvtec.com/research-teaching/datasets/mvtec-ad). MVTec publishes the dataset under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Attribute MVTec, use the data for noncommercial purposes, and follow the share-alike terms when distributing adaptations. Keep the extracted folders and their license material locally. Place the original category trees under `datasets/mvtec/`, so the bottle normals are at `datasets/mvtec/bottle/train/good/`. Preserve `test/` and `ground_truth/`. The same layout applies to `metal_nut` and `tile`.

```bash
uv sync --project ml --locked --python 3.11
uv run --project ml --locked python -m ml.dataset --category bottle
```

The validator checks layout, decodability, ground-truth mask dimensions, class coverage, and identical content shared by the official train and test sets. Pass `--data /path/to/mvtec` for a different data root.

### Train, calibrate, and evaluate bottle

```bash
uv run --project ml --locked python -m ml.train --category bottle --version bottle-v1
uv run --project ml --locked python -m ml.calibrate --category bottle --version bottle-v1
uv run --project ml --locked python -m ml.evaluate --category bottle --version bottle-v1
```

Repeat with `--category metal_nut --version nut-v1` or `--category tile --version tile-v1` for independent models. Training loads pretrained ResNet-18 feature weights through Anomalib/timm. The first explicit training run may fetch those weights. It uses 224 × 224 RGB inputs, batches of four, at most 20,000 coreset candidates, and a 5% Anomalib coreset. Automatic device selection prefers CUDA, then MPS, then CPU. Use `--device cpu` for comparable runs across machines. Accelerator errors during fitting or prediction trigger a CPU retry.

The seeded split holds out about 20% of distinct official training normals for calibration. The 95th percentile of their raw image scores defines a strict exceedance threshold. Final evaluation reads the untouched official test split. It records per-image scores, image AUROC and average precision, precision, recall, F1, and a thresholded confusion matrix with defective as the positive class. Pixel AUROC and average precision use pooled pixels on a 128 × 128 grid, verified defect masks, and zero masks for labeled normal images. Missing labels and unusable masks are excluded from the affected metric, and undefined metrics are stored as null.

Latency measures batch-size-one preprocessing and synchronized prediction after one calibration-image warmup. It excludes image decode and the request that switches devices during fallback. The report records per-device sample counts and means. A single mean is available for runs with timings from one device.

Each evaluation generates `roc.png`, `confusion.png`, and up to three `localization-*.png` comparisons showing the original, anomaly overlay, and ground-truth mask. After an API restart, **Model Evaluation** shows the comparison table, curve, matrix, samples, and run provenance for the current registered version of each category. Keep the test set out of model selection when reporting final performance.

Each run writes `models/<category>/<version>/` with the tensor-only checkpoint, copied config, hashed split manifest, runtime versions and checksums, calibration scores and threshold, and evaluation results. Training refuses to overwrite an existing version. A calibrated checkpoint can serve before its evaluation is recorded.

### Serve calibrated models

From the repository root, start the API with the ML environment and model serving enabled. Use a free port that matches the frontend API URL.

```bash
uv sync --project ml --locked --group serve
cd backend
uv run --locked alembic upgrade head
cd ..
DV_PATCHCORE_ENABLED=true uv run --project ml --locked --group serve python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 18001
```

PowerShell uses `$env:DV_PATCHCORE_ENABLED = "true"` before the same uvicorn command. Set `DV_MODELS_PATH` if the artifact directory differs from `models/`. The API registers calibrated artifacts on startup. Restart it after installing a new version. The server uses only the configured local artifact layout and checks checkpoint and metadata consistency. It keeps one loaded checkpoint per category and allows one model prediction at a time per process. Missing checkpoints return `503 model_not_ready`.

Start the frontend from the repository root. In PowerShell, set `$env:VITE_API_BASE_URL = "http://127.0.0.1:18001"` before the npm command.

```bash
VITE_API_BASE_URL=http://127.0.0.1:18001 npm --prefix frontend run dev -- --host 127.0.0.1
```

The Inspector shows raw anomaly scores, the calibrated threshold, and the original image, heatmap, and transparent overlay. Heatmap color and opacity use relative intensity within the individual image. The model decision uses the raw image score.

### Tests

```bash
uv run --project ml --locked --group serve python -m pytest -q ml/tests
```

These tests create a small artificial bottle directory and fit a temporary Anomalib checkpoint. They verify split isolation, calibration, evaluation, checkpoint loading, preprocessing consistency, API persistence, overlay alignment, cache reuse, and missing-checkpoint handling. Metrics from this fixture describe the test fixture only.
