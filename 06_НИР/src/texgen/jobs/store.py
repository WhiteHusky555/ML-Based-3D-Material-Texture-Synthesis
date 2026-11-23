"""Общее состояние задания и атомарная запись файлов на том Compose."""
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(os.environ.get("JOBS_ROOT", "/jobs"))
MAPS = ("height", "normal", "roughness", "ao", "albedo")


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=2048)
    noise_seed: int = Field(default=42, ge=0, le=2**32-1)
    seed: int = Field(default=42, ge=0, le=2**32-1)
    upscale: bool = False


def directory(job):
    return ROOT / str(UUID(str(job)))


def write(path, data):
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def save(folder, name, obj):
    write(folder / name, json.dumps(obj, ensure_ascii=False).encode())


def read(folder, name):
    return json.loads((folder / name).read_text(encoding="utf8"))
