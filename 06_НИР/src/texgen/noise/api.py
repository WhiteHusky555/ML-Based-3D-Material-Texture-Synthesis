"""HTTP-интерфейс генератора периодической карты высот."""
from typing import Literal

import numpy as np
from ..errors import service_app
from PIL import Image
from pydantic import Field

from ..http_maps import Request, encode
from . import generate

app = service_app("noise", title="Шум")


class Parameters(Request):
    kind: Literal["perlin", "voronoi", "combined"] = "combined"
    size: int = Field(512, ge=2, le=2048)
    cells: int = Field(8, ge=2, le=128)
    seed: int = Field(42, ge=0, le=2**32-1)


@app.post("/noise")
def noise(params: Parameters):
    height = generate(**params.model_dump())
    return {"height": encode(Image.fromarray(np.rint(height * 65535).astype("uint16")))}
