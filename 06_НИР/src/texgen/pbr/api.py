"""Периодические производные высоты и приближённые карты материала."""
import numpy as np
from ..errors import service_app
from PIL import Image
from pydantic import Field

from ..http_maps import Request, decode, encode

app = service_app("pbr", title="PBR")


class Material(Request):
    height: str = Field(min_length=1, max_length=12000000)
    albedo: str = Field(min_length=1, max_length=20000000)
    strength: float = Field(4, ge=0, le=64)
    roughness: float = Field(0.65, ge=0, le=1)


@app.post("/pbr")
def render(params: Material):
    color = decode(params.albedo, {"RGB"})
    height = decode(params.height, {"I;16", "L"})
    scale = 255 if height.mode == "L" else 65535
    h = np.asarray(height, dtype=np.float32) / scale
    if height.size != color.size:
        h = np.asarray(Image.fromarray(h).resize(color.size, Image.Resampling.BILINEAR))
    left, right = np.roll(h, 1, axis=1), np.roll(h, -1, axis=1)
    up, down = np.roll(h, 1, axis=0), np.roll(h, -1, axis=0)
    normal = np.stack(((left-right)*params.strength/2, (down-up)*params.strength/2, np.ones_like(h)), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    cavity = np.maximum((left+right+up+down)/4 - h, 0)
    ao = np.clip(1 - params.strength*cavity, 0, 1)
    return {
        "height": encode(Image.fromarray(np.rint(h*65535).astype("uint16"))),
        "normal": encode(Image.fromarray(np.rint((normal+1)*127.5).astype("uint8"))),
        "roughness": encode(Image.new("L", color.size, round(params.roughness*255))),
        "ao": encode(Image.fromarray(np.rint(ao*255).astype("uint8"))),
    }
