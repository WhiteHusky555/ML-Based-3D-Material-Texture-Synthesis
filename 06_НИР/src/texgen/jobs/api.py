from typing import Annotated, Literal
from uuid import UUID

from fastapi import Header
from fastapi.responses import FileResponse
from filelock import FileLock

from ..errors import ServiceError, service_app
from . import broker, store

app = service_app("jobs", title="Задания НИР")


@app.post("/jobs", status_code=202)
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


@app.get("/jobs/{job}")
def status(job: UUID):
    folder = store.directory(job)
    if not (folder / "request.json").exists():
        raise ServiceError(404, "job_not_found", "Задание не найдено.")
    return store.read(folder, "state.json")


@app.get("/jobs/{job}/maps/{name}")
def artifact(job: UUID, name: Literal["albedo", "height", "normal", "roughness", "ao"]):
    if status(job)["status"] != "completed":
        raise ServiceError(409, "result_pending", "Результат недоступен.")
    return FileResponse(store.directory(job) / f"{name}.png", media_type="image/png")
