from typing import Annotated, Literal
from uuid import UUID

from fastapi import Header
from fastapi.responses import FileResponse
from filelock import FileLock

from ..contracts import Accepted, JobState, error
from ..errors import ServiceError, service_app
from . import broker, store

app = service_app("jobs", title="Задания НИР")


@app.post("/jobs", status_code=202, summary="Поставить задание в очередь", response_model=Accepted,
          responses={409: error("idempotency_conflict"), 422: error("invalid_request"),
                     503: error("queue_unavailable (Retry-After в секундах)")})
def submit(params: store.Parameters, idempotency_key: Annotated[UUID, Header()]):
    folder = store.directory(idempotency_key)
    folder.mkdir(parents=True, exist_ok=True)
    with FileLock(str(folder / "submit.lock")):
        if (folder / "request.json").exists():
            if store.read(folder, "request.json") != params.model_dump():
                raise ServiceError(409, "idempotency_conflict", "Ключ уже занят другим запросом.")
        else:
            store.save(folder, "state.json", {"status": "queued", "stage": "noise"})
            store.save(folder, "request.json", params.model_dump())
        if not (folder / "accepted").exists():
            try:
                with broker.channel() as ch:
                    broker.publish(ch, "noise", idempotency_key)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception("Ошибка публикации задания")
                raise ServiceError(503, "queue_unavailable", "Повторите запрос с тем же ключом.", retry_after=2) from exc
            store.write(folder / "accepted", b"")
    return {"job_id": str(idempotency_key)}


@app.get("/jobs/{job}", summary="Получить состояние задания", response_model=JobState,
         response_model_exclude_unset=True, responses={404: error("job_not_found"), 422: error("invalid_request")})
def status(job: UUID):
    folder = store.directory(job)
    if not (folder / "request.json").exists():
        raise ServiceError(404, "job_not_found", "Задание не найдено.")
    return store.read(folder, "state.json")


@app.get("/jobs/{job}/maps/{name}", summary="Скачать карту PNG", response_class=FileResponse,
         responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}},
                    404: error("job_not_found"), 409: error("result_pending"), 422: error("invalid_request")})
def artifact(job: UUID, name: Literal["albedo", "height", "normal", "roughness", "ao"]):
    if status(job)["status"] != "completed":
        raise ServiceError(409, "result_pending", "Результат недоступен.")
    return FileResponse(store.directory(job) / f"{name}.png", media_type="image/png")
