from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps


def localization(path: Path, image, anomaly, mask):
    size = (256, 192)
    contained = ImageOps.contain(image, size)
    field = np.asarray(Image.fromarray(anomaly).resize(contained.size, Image.Resampling.BILINEAR))
    span = float(np.ptp(field))
    intensity = ((field - field.min()) / span * 255).astype(np.uint8) if span else np.zeros(field.shape, dtype=np.uint8)
    palette = np.stack([intensity, np.zeros_like(intensity), 255 - intensity], axis=-1)
    heatmap = Image.fromarray(palette)
    overlay = Image.composite(heatmap, contained, Image.fromarray(intensity // 2))
    truth = mask.resize(contained.size, Image.Resampling.NEAREST).convert("RGB")
    sheet = Image.new("RGB", (size[0] * 3, size[1] + 24), "#12243a")
    draw = ImageDraw.Draw(sheet)
    for index, (name, pixels) in enumerate(zip(("Original", "Anomaly overlay", "Ground truth"), (contained, overlay, truth), strict=True)):
        x = index * size[0]
        sheet.paste(pixels, (x + (size[0] - pixels.width) // 2, 24 + (size[1] - pixels.height) // 2))
        draw.text((x + 8, 6), name, fill="white")
    sheet.save(path)


def plots(run, curve, matrix):
    from matplotlib.figure import Figure

    fig = Figure(figsize=(5, 4), layout="constrained")
    axis = fig.subplots()
    axis.plot([0, 1], [0, 1], linestyle="--", color="gray")
    if curve:
        axis.plot([row["fpr"] for row in curve], [row["tpr"] for row in curve], color="#17678b")
    else:
        axis.text(0.5, 0.45, "ROC unavailable: both labels required", ha="center")
    axis.set(xlabel="False positive rate", ylabel="True positive rate", title="Image-level ROC", xlim=(0, 1), ylim=(0, 1.02))
    fig.savefig(run / "roc.png", dpi=140)
    fig = Figure(figsize=(5, 4), layout="constrained")
    axis = fig.subplots()
    axis.imshow(matrix, cmap="Blues", vmin=0)
    for row in range(2):
        for column in range(2):
            value = matrix[row][column]
            axis.text(column, row, str(value), ha="center", va="center",
                      color="white" if value > max(map(max, matrix)) / 2 else "#12243a")
    axis.set(xticks=[0, 1], yticks=[0, 1], xticklabels=["Normal", "Defective"],
             yticklabels=["Normal", "Defective"], xlabel="Predicted", ylabel="Actual", title="Image-level confusion matrix")
    fig.savefig(run / "confusion.png", dpi=140)
