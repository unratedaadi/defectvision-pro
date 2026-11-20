"""Use Anomalib's PatchCore model with a bounded feature bank."""

import os
import warnings

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import torch
from anomalib.models.image.patchcore.torch_model import PatchcoreModel
from PIL import Image, ImageOps
from torchvision import transforms


def choose_device(requested):
    available = {"cpu": True, "mps": torch.backends.mps.is_available(), "cuda": torch.cuda.is_available()}
    if requested == "auto":
        return next(device for device in ("cuda", "mps", "cpu") if available[device])
    if not available[requested]:
        warnings.warn(f"{requested} unavailable. Using CPU.", stacklevel=2)
        return "cpu"
    return requested


def build(config, *, pretrained):
    model = PatchcoreModel(
        layers=config["layers"], backbone=config["backbone"],
        pre_trained=pretrained, num_neighbors=config["num_neighbors"],
    )
    return model


def preprocessing(config):
    size = config["image_size"]
    return transforms.Compose([
        transforms.Resize((size, size), antialias=True),
        transforms.ToTensor(),
        transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
    ])


def read_image(path):
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


@torch.no_grad()
def fit(config, paths, device, *, pretrained=True):
    torch.manual_seed(config["seed"])
    generator = torch.Generator().manual_seed(config["seed"])
    transform = preprocessing(config)
    model = build(config, pretrained=pretrained).to(device).train()
    model.feature_extractor.eval()
    batch_size = config["batch_size"]
    budget = config["max_patches"]
    embeddings = []
    for offset in range(0, len(paths), batch_size):
        subset = paths[offset:offset + batch_size]
        batch = torch.stack([transform(read_image(path)) for path in subset]).to(device)
        features = model(batch).cpu()
        model.embedding_store.clear()
        patches = features.reshape(len(subset), -1, features.shape[-1])
        for index, rows in enumerate(patches, start=offset):
            quota = budget * (index + 1) // len(paths) - budget * index // len(paths)
            if quota:
                embeddings.append(rows[torch.randperm(len(rows), generator=generator)[:quota]])
    candidates = torch.cat(embeddings)
    if int(len(candidates) * config["coreset_ratio"]) < config["num_neighbors"]:
        raise ValueError("Coreset is smaller than num_neighbors. Increase the patch budget or ratio.")
    model = model.cpu()
    model.embedding_store.append(candidates)
    model.subsample_embedding(sampling_ratio=config["coreset_ratio"])
    return model.eval()


def load_model(path, config, device):
    model = build(config, pretrained=False)
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    try:
        return model.to(device).eval()
    except (RuntimeError, NotImplementedError):
        if device == "cpu":
            raise
        warnings.warn(f"Could not place PatchCore on {device}. Using CPU.", stacklevel=2)
        return model.cpu().eval()


class Predictor:
    def __init__(self, model, config):
        self.model = model
        self.transform = preprocessing(config)
        self.device = model.memory_bank.device.type

    @torch.inference_mode()
    def __call__(self, image):
        sample = self.transform(image.convert("RGB")).unsqueeze(0)
        try:
            output = self.model(sample.to(self.device))
        except (RuntimeError, NotImplementedError):
            if self.device == "cpu":
                raise
            warnings.warn(f"PatchCore prediction failed on {self.device}. Retrying on CPU.", stacklevel=2)
            self.device = "cpu"
            self.model = self.model.cpu()
            output = self.model(sample)
        score = output.pred_score.reshape(-1)
        heatmap = output.anomaly_map.squeeze()
        if score.numel() != 1 or heatmap.ndim != 2:
            raise ValueError("Unexpected Anomalib inference output dimensions.")
        if not torch.isfinite(score).all() or not torch.isfinite(heatmap).all():
            raise ValueError("PatchCore returned non-finite output.")
        return score.item(), heatmap.cpu().numpy()
