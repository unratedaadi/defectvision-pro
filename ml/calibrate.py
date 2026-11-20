"""Calibrate the image decision threshold on held-out train/good images."""

import math

from ml.artifacts import cli, load_metadata, read_config, read_json, verified_path, write_json


def main():
    parser, args = cli(__doc__)
    from ml.patchcore import Predictor, choose_device, load_model, read_image

    meta = load_metadata(args.run, args.category)
    output = args.run / "threshold.json"
    if output.exists() or (args.run / "evaluation.json").exists():
        parser.error("This version is already calibrated. Use a new version to change calibration.")
    config = read_config(args.run / "config.yaml")
    split = read_json(args.run / "split.json")
    device = choose_device(args.device)
    predictor = Predictor(load_model(args.run / "patchcore.pt", config, device), config)
    scores = []
    for row in split["calibration"]:
        score, _ = predictor(read_image(verified_path(args.data, row)))
        scores.append({"path": row["path"], "score": score})
    ordered = sorted(row["score"] for row in scores)
    quantile = config["calibration_quantile"]
    cutoff = ordered[math.ceil(len(ordered) * quantile) - 1]
    threshold = math.nextafter(cutoff, math.inf)
    write_json(output, {
        "category": args.category, "version": args.version, "threshold": threshold,
        "quantile": quantile, "method": "nearest-rank quantile of held-out normal scores, strict exceedance",
        "device": predictor.device, "sha256": meta["sha256"], "scores": scores,
    })
    print(f"Saved {output} (threshold={threshold:g}, n={len(scores)})")


if __name__ == "__main__":
    main()
