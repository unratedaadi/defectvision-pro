# DefectVision Pro

## EDL project report

DefectVision Pro is a local visual inspection application for bottles, metal nuts, and ceramic tiles. It flags unusual images, shows where the anomaly score is concentrated, and records each result with its model version and decision threshold. The workflow gives an operator an image, a heatmap, and a PDF record to review.

### System design

React and TypeScript provide the inspection, batch, history, analytics, and model evaluation screens. FastAPI validates image uploads and selects a category-specific PatchCore checkpoint. SQLAlchemy and SQLite record predictions, timestamps, and media locations. The original image, anomaly heatmap, and overlay live in local storage. Recharts renders analytics from saved inspection records, and ReportLab builds PDFs from those records. See the [architecture overview](architecture.md), [API guide](frontend-api.md), and [training guide](../ml/README.md).

### Training and evaluation

Each category uses an independent Anomalib PatchCore model with a pretrained ResNet-18. The pipeline resizes RGB input to 224 × 224 and extracts patch embeddings from layers 2 and 3. It caps the coreset candidate pool at 20,000 patches and retains a 5% representative subset. During inference, distances to normal training patches produce a pixel anomaly map and an image-level score. The raw score is a distance-based statistic. A score at or above the stored category threshold produces a defective decision.

Training used normal images from the official MVTec AD training split. A seeded 20% holdout from `train/good` supplied the calibration scores (42 bottle, 44 metal nut, 46 tile). The stored threshold is the next representable value above the nearest-rank 95th percentile of those scores. This makes a score equal to that percentile a normal decision. The untouched official test split provided image labels and defect masks for the final evaluation.

| Category | Test images | Image AUROC | Pixel AUROC | Precision | Recall | F1 | Mean latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Bottle | 83 | 1.0000 | 0.9764 | 0.9844 | 1.0000 | 0.9921 | 19.6 ms |
| Metal Nut | 115 | 0.9936 | 0.9827 | 0.9888 | 0.9462 | 0.9670 | 19.7 ms |
| Tile | 117 | 0.9928 | 0.9287 | 1.0000 | 0.9286 | 0.9630 | 18.7 ms |

All runs use version `mvtec-edl-v1`. Pixel AUROC uses ground-truth masks and anomaly maps on a 128 × 128 grid. Mean latency uses batch size one on Apple Silicon MPS and includes preprocessing and synchronized prediction. Image decoding and HTTP overhead are outside that measurement. The model folders contain the raw metrics, ROC curves, confusion matrices, and localization examples.

At the calibrated thresholds, Bottle missed zero defects and flagged one normal image. Metal Nut missed five defects and flagged one normal image. Tile missed six defects and flagged zero normal images. These results describe the MVTec AD test conditions. Different camera geometry, lighting, or parts require separate validation. Human verification remains necessary for safety-critical manufacturing.

### References

- Paul Bergmann et al., [MVTec AD dataset and license](https://www.mvtec.com/research-teaching/datasets/mvtec-ad). Dataset imagery is used for a noncommercial classroom demonstration under CC BY-NC-SA 4.0.
- Karsten Roth et al., [Towards Total Recall in Industrial Anomaly Detection](https://arxiv.org/abs/2106.08265), CVPR 2022.

## Five-minute demonstration

### Before presenting

1. Keep the repository on the demo Mac. Confirm each of `models/{bottle,metal_nut,tile}/mvtec-edl-v1/` has `patchcore.pt`, `model.json`, `threshold.json`, and `evaluation.json`. These model files are Git-ignored.
2. Confirm the six local PNGs in `storage/demo-samples/`. They are copied from the official test split, remain outside Git, and can be uploaded without mounting the dataset. Keep `MVTec-AD-license.txt` beside them.
3. The source dataset was readable at `/Volumes/DefectVisionStage/mvtec` during rehearsal. It is a RAM disk and will disappear after a restart. Preserve or restore the full category directories and licenses on persistent storage if you plan to rerun training or evaluation. The application serves inference from the persistent model folders.
4. Start both services from the repository root in separate terminals. Keep them running during the presentation.

```bash
DV_PATCHCORE_ENABLED=true DV_PATCHCORE_DEVICE=mps \
OMP_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 \
uv run --project ml --locked --group serve python -m uvicorn \
  app.main:app --app-dir backend --host 127.0.0.1 --port 18003
```

```bash
VITE_API_BASE_URL=http://127.0.0.1:18003 \
npm --prefix frontend run dev -- --host 127.0.0.1
```

Open [DefectVision Pro](http://127.0.0.1:5173/) in Chrome. Confirm the [health endpoint](http://127.0.0.1:18003/api/health) reports a ready database and the [model endpoint](http://127.0.0.1:18003/api/models) lists all three categories as ready. Run one known sample as a warmup.

| Local sample | Original MVTec AD path | Expected result | Reference score | Threshold |
| --- | --- | --- | ---: | ---: |
| `01-bottle-normal.png` | `bottle/test/good/000.png` | Normal | 8.6887 | 9.2017 |
| `02-bottle-defective-broken-large.png` | `bottle/test/broken_large/000.png` | Defective | 20.4875 | 9.2017 |
| `03-metal-nut-normal.png` | `metal_nut/test/good/000.png` | Normal | 13.3134 | 14.0089 |
| `04-metal-nut-defective-bent.png` | `metal_nut/test/bent/000.png` | Defective | 17.3062 | 14.0089 |
| `05-tile-normal.png` | `tile/test/good/000.png` | Normal | 9.8137 | 11.8356 |
| `06-tile-defective-crack.png` | `tile/test/crack/000.png` | Defective | 20.8193 | 11.8356 |

### Presentation sequence

1. **0:00–0:45.** Explain why a model learns the appearance of normal parts. Show the model version and the three ready categories.
2. **0:45–2:00.** In AI Inspector, select Bottle and upload the normal and broken bottle in sequence. Read each raw score and threshold. Switch from Original to Heatmap, then to Overlay, and adjust Heatmap opacity.
3. **2:00–2:45.** Select Tile and run the cracked tile. Explain that the heatmap indicates where the model found unusual patches. Keep the metal-nut pair available for a follow-up.
4. **2:45–3:45.** Open Inspection History and select **View** beside the defective bottle result. Export **Download PDF** and open it to show the recorded model version, score, threshold, and image evidence.
5. **3:45–5:00.** Open Analytics & Reports to show live counts and export the aggregate PDF. Open Model Evaluation to discuss the official test results. The analytics defect rate reflects the mix of uploaded samples, including rehearsals.

Chrome granted camera access and the preview reached **Camera active** on the demo Mac. Stopping the preview returned it to **Camera idle**. No live prediction was run on a physical part. Keep uploads as the main demonstration. Include live inspection only after a successful prediction with a real part in the same Chrome profile and presentation setup.

### Rehearsal record

The broken bottle uploaded through Chrome returned **Defective** with a raw score of 20.4875 and a threshold of 9.2017. The heatmap and overlay rendered, and the slider changed the overlay opacity. History saved inspection `75a873c5-71dd-4cc2-97fc-967fa6de44a8`. Chrome downloaded the individual and aggregate PDFs. Analytics reconciled with the saved records at seven inspections, three normal and four defective.
