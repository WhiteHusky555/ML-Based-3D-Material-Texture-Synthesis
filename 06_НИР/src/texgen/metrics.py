"""Оценка стыков и следования ячейкам Вороного в контрольной серии."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def cell_edges(size, cells, seed):
    """Границы смены ближайшего центра на периодической сетке texgen.noise."""
    sites = np.random.default_rng(seed).random((cells, cells, 2))
    axis = np.arange(size) * cells / size
    x, y = np.meshgrid(axis, axis)
    nearest = np.full(x.shape, np.inf)
    labels = np.zeros(x.shape, dtype=np.int32)
    for row, col in np.ndindex(cells, cells):
        sx, sy = sites[row, col]
        dx = np.abs(x - (col + sx))
        dy = np.abs(y - (row + sy))
        distance = np.minimum(dx, cells - dx)**2 + np.minimum(dy, cells - dy)**2
        closer = distance < nearest
        nearest[closer] = distance[closer]
        labels[closer] = row * cells + col
    return (labels != np.roll(labels, 1, axis=0)) | (labels != np.roll(labels, 1, axis=1))


def measure(image, edges):
    """Яркость по шкале 0–255, маска границ в координатах входного изображения."""
    gray = np.asarray(image.convert("L"), dtype=float)
    if gray.shape != edges.shape or min(gray.shape) < 2 or not edges.any():
        raise ValueError("Проверьте размер изображения и непустую маску границ")
    result = {}
    for axis, name in ((0, "y"), (1, "x")):
        seam = float(np.abs(gray.take(0, axis) - gray.take(-1, axis)).mean())
        inside = float(np.abs(np.diff(gray, axis=axis)).mean())
        result[name] = dict(seam=seam, inside=inside, ratio=seam / inside if inside >= 1 else None)

    smooth = gray
    for axis in (0, 1):
        smooth = sum(w * np.roll(smooth, offset, axis) for offset, w in
                     zip(range(-2, 3), (1, 4, 6, 4, 1))) / 16
    gradient = np.hypot(smooth - np.roll(smooth, 1, 0), smooth - np.roll(smooth, 1, 1))
    strong = gradient >= max(1., float(np.percentile(gradient, 90)))
    nearby = np.zeros_like(strong)
    for dy, dx in np.ndindex(5, 5):
        nearby |= np.roll(strong, (dy-2, dx-2), axis=(0, 1))
    shifted = np.roll(edges, (edges.shape[0]//3, edges.shape[1]//3), axis=(0, 1))
    coverage = float(nearby[edges].mean())
    control = float(nearby[shifted].mean())
    result.update(edge_density=float(strong.mean()), coverage=coverage, shifted_coverage=control,
                  coverage_gain=coverage-control)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--noise-seed", type=int, required=True, choices=(12, 37))
    args = parser.parse_args()
    with Image.open(args.image) as image:
        print(json.dumps(measure(image, cell_edges(512, 8, args.noise_seed)), indent=2))
