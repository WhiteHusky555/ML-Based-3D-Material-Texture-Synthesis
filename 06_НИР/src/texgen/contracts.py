"""Схемы HTTP-ответов сервисного стенда."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field


Png = Annotated[str, Field(json_schema_extra={"contentEncoding": "base64", "contentMediaType": "image/png"})]


class NoiseMap(BaseModel):
    height: Png


class MaterialMaps(NoiseMap):
    normal: Png
    roughness: Png
    ao: Png


class ModelVersion(BaseModel):
    version: str
    revision: int
    sha256: str


class Generated(BaseModel):
    albedo: Png
    model: ModelVersion


class Ready(BaseModel):
    model: ModelVersion
    update_error: str | None


class Accepted(BaseModel):
    job_id: UUID


class JobState(BaseModel):
    status: Literal["queued", "running", "waiting", "completed", "failed"]
    stage: Literal["noise", "generation", "pbr"]
    model: ModelVersion | None = None
    attempts: int | None = None
    code: str | None = None


class InvalidField(BaseModel):
    location: list[str | int]
    type: str


class ErrorDetail(BaseModel):
    service: str
    code: str
    message: str
    fields: list[InvalidField] | None = None
    incident_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


def error(description):
    return {"model": ErrorResponse, "description": description}
