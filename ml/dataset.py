"""Validate MVTec AD and freeze a content-addressed split manifest."""

import argparse
import hashlib
import json
import random
from pathlib import Path

from PIL import Image

CATEGORIES = ("bottle", "metal_nut", "tile")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "datasets" / "mvtec"
EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def image_info(root, path):
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"Image escapes dataset root: {path}")
    try:
        with Image.open(path) as image:
            size = image.size
            image.load()
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise ValueError(f"Unreadable image: {path}") from error
    return {"path": path.relative_to(root).as_posix(), "sha256": digest(path)}, size


def images(folder):
    return sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in EXTENSIONS)


def discover(root, category, seed=42, fraction=0.2):
    if category not in CATEGORIES or not 0 < fraction < 1:
        raise ValueError("Expected a supported category and a calibration fraction between zero and one.")
    root = root.resolve()
    directory = root / category
    train = directory / "train"
    test = directory / "test"
    if not (train / "good").is_dir() or not (test / "good").is_dir():
        raise ValueError(f"Missing official train/good or test/good folders under {directory}")
    if any(path.is_dir() and not path.name.startswith(".") and path.name != "good" for path in train.iterdir()):
        raise ValueError(f"Unexpected training class under {train}")

    normals = [image_info(root, path)[0] for path in images(train / "good")]
    # Keep copies of identical training images on the same side of the split.
    groups = sorted({row["sha256"] for row in normals})
    if len(groups) < 2:
        raise ValueError("At least two distinct official training images are required.")
    random.Random(seed).shuffle(groups)
    count = min(len(groups) - 1, max(1, round(len(groups) * fraction)))
    calibration = set(groups[:count])
    known = set(groups)

    tests = []
    for folder in sorted(test.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        for path in images(folder):
            row, size = image_info(root, path)
            if row["sha256"] in known:
                raise ValueError(f"Official training and test share identical content: {path}")
            row.update(label=int(folder.name != "good"), defect=folder.name, mask=None)
            if row["label"]:
                mask = directory / "ground_truth" / folder.name / f"{path.stem}_mask.png"
                if not mask.is_file():
                    raise ValueError(f"Missing ground truth mask: {mask}")
                row["mask"], mask_size = image_info(root, mask)
                if size != mask_size:
                    raise ValueError(f"Ground truth dimensions differ from image: {mask}")
            tests.append(row)
    if {row["label"] for row in tests} != {0, 1}:
        raise ValueError("Expected both normal and defective official test images.")
    return {
        "category": category, "seed": seed, "calibration_fraction": fraction,
        "fit": [row for row in normals if row["sha256"] not in calibration],
        "calibration": [row for row in normals if row["sha256"] in calibration], "test": tests,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--category", choices=CATEGORIES, required=True)
    args = parser.parse_args()
    try:
        manifest = discover(args.data, args.category)
    except ValueError as error:
        parser.exit(2, f"Dataset validation failed: {error}\n")
    print(json.dumps({key: len(manifest[key]) for key in ("fit", "calibration", "test")}, indent=2))


if __name__ == "__main__":
    main()
