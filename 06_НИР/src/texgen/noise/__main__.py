import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from . import generate

parser = argparse.ArgumentParser(description="Генерация периодических карт шума")
parser.add_argument("--output", type=Path, default=Path("examples/noise"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
for kind in ("perlin", "voronoi", "combined"):
    field = generate(kind)
    Image.fromarray(np.rint(field * 65535).astype("uint16")).save(args.output / f"{kind}.png")
    preview = np.tile(np.rint(field * 255).astype("uint8"), (2, 2))
    Image.fromarray(preview).save(args.output / f"{kind}_2x2.png")
