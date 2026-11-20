"""Evaluate the frozen checkpoint and threshold on the official MVTec test split."""

from datetime import UTC, datetime
from importlib.metadata import version
import platform
from math import isfinite
from time import perf_counter

from ml.artifacts import cli, load_metadata, read_config, read_json, verified_path, write_json
from ml.dataset import digest


def main():
    _, args = cli(__doc__)
    import numpy as np
    from PIL import Image
    from ml.metrics import binary_metrics, pixel_metrics
    from ml.evaluation_visuals import localization, plots
    from ml.patchcore import Predictor, choose_device, load_model, read_image, torch

    meta = load_metadata(args.run, args.category)
    config = read_config(args.run / "config.yaml")
    threshold_path = args.run / "threshold.json"
    calibration = read_json(threshold_path)
    if (calibration["category"], calibration["version"], calibration["sha256"]) != (
        args.category, args.version, meta["sha256"],
    ):
        raise ValueError("Threshold metadata does not belong to this checkpoint.")
    threshold = calibration["threshold"]
    if not isfinite(threshold):
        raise ValueError("Threshold must be finite.")
    split = read_json(args.run / "split.json")
    device = choose_device(args.device)
    predictor = Predictor(load_model(args.run / "patchcore.pt", config, device), config)
    grid = (config["pixel_metric_size"],) * 2
    rows, pixel_labels, pixel_scores = [], [], []
    samples = []
    if split["calibration"]:
        predictor(read_image(verified_path(args.data, split["calibration"][0])))
    hardware = {"platform": platform.platform(), "machine": platform.machine(),
                "processor": platform.processor() or platform.machine()}
    if device == "cuda":
        hardware["accelerator"] = torch.cuda.get_device_name()
    elif device == "mps":
        hardware["accelerator"] = "Apple Metal"
    for row in split["test"]:
        image = read_image(verified_path(args.data, row))
        before = predictor.device
        start = perf_counter()
        score, anomaly = predictor(image)
        latency = (perf_counter() - start) * 1000 if predictor.device == before else None
        actual = row.get("label")
        rows.append({"path": row["path"], "label": actual, "defect": row.get("defect"),
                     "score": score, "prediction": int(score >= threshold),
                     "latency_ms": latency, "device": predictor.device})
        if actual == 1 and row.get("mask"):
            with Image.open(verified_path(args.data, row["mask"])) as mask:
                truth = mask.convert("L").point(lambda value: 255 if value else 0)
                if truth.size != image.size or not truth.getbbox():
                    continue
                label = np.asarray(truth.resize(grid, Image.Resampling.NEAREST)) > 0
                if len(samples) < 3:
                    name = f"localization-{len(samples) + 1}.png"
                    localization(args.run / name, image, anomaly, truth)
                    samples.append({"file": name, "image": row["path"], "sha256": digest(args.run / name)})
        elif actual == 0:
            label = np.zeros(grid, dtype=bool)
        else:
            continue
        pixel_labels.append(label.ravel())
        pixel_scores.append(np.asarray(Image.fromarray(anomaly).resize(grid, Image.Resampling.BILINEAR)).ravel())
    metrics, curve = binary_metrics(rows)
    metrics.update(pixel_metrics(pixel_labels, pixel_scores))
    timings = {}
    for row in rows:
        if row["latency_ms"] is not None:
            timings.setdefault(row["device"], []).append(row["latency_ms"])
    latency_by_device = {name: {"count": len(values), "mean_ms": sum(values) / len(values)}
                         for name, values in timings.items()}
    metrics["average_inference_latency_ms"] = (
        next(iter(latency_by_device.values()))["mean_ms"] if len(latency_by_device) == 1 else None
    )
    plots(args.run, curve, metrics["confusion_matrix"])
    output = args.run / "evaluation.json"
    write_json(output, {
        "category": args.category, "version": args.version, "threshold": threshold,
        "evaluated_at": datetime.now(UTC).isoformat(), "device": predictor.device, "hardware": hardware,
        "dataset_split": "test", "calibration": {
            "method": calibration["method"], "sample_count": len(calibration["scores"]),
            "quantile": calibration["quantile"], "split": "held-out train/good",
        },
        "packages": {name: version(name) for name in meta["packages"]},
        "sha256": {**meta["sha256"], "threshold.json": digest(threshold_path)},
        "pixel_metric_size": list(grid), "test_count": len(rows),
        "labeled_count": sum(row["label"] in (0, 1) for row in rows), "pixel_image_count": len(pixel_labels),
        "latency_scope": "batch size 1; preprocessing and synchronized prediction; excludes image decode",
        "latency_by_device": latency_by_device,
        "inference_devices": sorted({row["device"] for row in rows}),
        "metrics": metrics, "images": rows, "roc": curve, "samples": samples,
    })
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
