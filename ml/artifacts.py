"""Shared artifact paths, configuration, and atomic writes."""

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from ml.dataset import CATEGORIES, DEFAULT_DATA, ROOT, digest

CONFIGS = Path(__file__).resolve().parent / "configs"


def cli(description, *, training=False):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--category", choices=CATEGORIES, required=True)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--models", type=Path, default=ROOT / "models")
    parser.add_argument("--version", required=not training)
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    args = parser.parse_args()
    args.version = args.version or datetime.now(UTC).strftime("patchcore-%Y%m%dT%H%M%S%fZ")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", args.version):
        parser.error("Version must be a safe, single path component.")
    args.run = args.models / args.category / args.version
    return parser, args


def write_json(path, data):
    temp = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temp, path)
    finally:
        if temp:
            temp.unlink(missing_ok=True)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_config(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def verified_path(root, row):
    root = root.resolve()
    path = (root / row["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file() or digest(path) != row["sha256"]:
        raise ValueError(f"Dataset file differs from the training manifest: {row['path']}")
    return path


def load_metadata(run, category):
    meta = read_json(run / "model.json")
    if meta["category"] != category or meta["version"] != run.name:
        raise ValueError("Checkpoint metadata does not match the requested category and version.")
    for name in ("patchcore.pt", "config.yaml", "split.json"):
        if digest(run / name) != meta["sha256"][name]:
            raise ValueError(f"Artifact checksum mismatch: {name}")
    return meta
