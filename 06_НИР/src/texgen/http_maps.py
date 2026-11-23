"""Передача карт между локальными сервисами в формате PNG/base64."""
import base64
import binascii
from io import BytesIO

from .errors import ServiceError
from PIL import Image
from pydantic import BaseModel, ConfigDict


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


def encode(image):
    stream = BytesIO()
    image.save(stream, format="PNG")
    return base64.b64encode(stream.getvalue()).decode("ascii")


def decode(data, modes):
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ServiceError(422, "invalid_base64", "Некорректная кодировка карты.") from exc
    try:
        with Image.open(BytesIO(raw), formats=["PNG"]) as image:
            if image.width != image.height or not 2 <= image.width <= 2048 or image.mode not in modes:
                raise ServiceError(422, "unsupported_map", "Размер или режим карты не поддерживается.")
            return image.copy()
    except (ValueError, OSError, binascii.Error, Image.DecompressionBombError) as exc:
        raise ServiceError(422, "invalid_png", "Некорректная PNG-карта.") from exc
