"""Fit one pretrained Anomalib PatchCore model on official train/good images."""

import shutil
from datetime import UTC, datetime
from importlib.metadata import version
from tempfile import TemporaryDirectory
from pathlib import Path

from ml.artifacts import CONFIGS, cli, read_config, verified_path, write_json
from ml.dataset import digest, discover


def main():
    parser, args = cli(__doc__, training=True)
    config_path = CONFIGS / f"{args.category}.yaml"
    config = read_config(config_path)
    if config["category"] != args.category:
        parser.error("Configuration category does not match the request.")
    try:
        split = discover(args.data, args.category, config["seed"], config["calibration_fraction"])
    except ValueError as error:
        parser.error(str(error))
    if args.run.exists():
        parser.error(f"Model version already exists: {args.run}")

    from ml.patchcore import choose_device, fit, torch

    paths = [verified_path(args.data, row) for row in split["fit"]]
    device = choose_device(args.device)
    print(f"Fitting {args.category} on {device} with {len(paths)} normal images", flush=True)
    try:
        model = fit(config, paths, device)
    except (RuntimeError, NotImplementedError):
        if device == "cpu":
            raise
        print(f"Training on {device} failed. Retrying on CPU.", flush=True)
        device = "cpu"
        model = fit(config, paths, device)

    args.run.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.run.parent, prefix=".training-") as temporary:
        staging = Path(temporary) / "artifact"
        staging.mkdir()
        torch.save(model.state_dict(), staging / "patchcore.pt")
        shutil.copyfile(config_path, staging / "config.yaml")
        write_json(staging / "split.json", split)
        write_json(staging / "model.json", {
            "category": args.category, "version": args.version,
            "created_at": datetime.now(UTC).isoformat(), "fit_device": device,
            "packages": {name: version(name) for name in ("anomalib", "torch", "torchvision", "timm", "numpy", "scikit-learn", "pillow")},
            "sha256": {name: digest(staging / name) for name in ("patchcore.pt", "config.yaml", "split.json")},
        })
        staging.rename(args.run)
    print(f"Saved {args.run}")


if __name__ == "__main__":
    main()
