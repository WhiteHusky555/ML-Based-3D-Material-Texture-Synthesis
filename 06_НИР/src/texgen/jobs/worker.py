"""Обработка одного этапа. ACK следует после подтверждения следующей публикации."""
import argparse
import base64
import logging
import time
from uuid import UUID

import httpx
from filelock import FileLock

from . import broker, store


def compute(client, stage, folder, params):
    def png(name):
        return base64.b64encode((folder / name).read_bytes()).decode()
    if stage == "noise":
        route, payload = "noise", {"seed": params.noise_seed}
    elif stage == "generation":
        route = "generate"
        payload = dict(height=png("noise.png"), prompt=params.prompt, seed=params.seed, upscale=params.upscale)
    else:
        route = "pbr"
        payload = dict(height=png("noise.png"), albedo=png("albedo.png"))
    response = client.post(f"http://{stage}:8000/{route}", json=payload)
    response.raise_for_status()
    result = response.json()
    keys = {"noise": ["height"], "generation": ["albedo"], "pbr": ["normal", "height", "roughness", "ao"]}
    for key in keys[stage]:
        filename = "noise.png" if stage == "noise" else f"{key}.png"
        store.write(folder / filename, base64.b64decode(result[key], validate=True))
    if stage == "generation":
        store.save(folder, "model.json", result["model"])


def process(client, stage, job, send):
    folder = store.directory(job)
    with FileLock(str(folder / "worker.lock")):
        state = store.read(folder, "state.json")
        if state["status"] == "failed":
            return
        index = broker.STAGES.index(stage)
        next_stage = broker.STAGES[index+1] if index+1 < len(broker.STAGES) else None
        marker = folder / f"{stage}.done"
        if not marker.exists():
            params = store.Parameters.model_validate(store.read(folder, "request.json"))
            store.save(folder, "state.json", dict(status="running", stage=stage))
            try:
                compute(client, stage, folder, params)
            except httpx.HTTPStatusError as exc:
                error = exc.response.json().get("error", {})
                code = error.get("code", "service_error")
                if stage == "generation" and code in {"model_busy", "model_unavailable"}:
                    store.save(folder, "state.json", dict(status="waiting", stage=stage, code=code))
                    return "retry"
                if exc.response.status_code < 500:
                    store.save(folder, "state.json", dict(status="failed", stage=stage, code=code))
                    return
                return retry(folder, stage, code)
            except httpx.RequestError:
                return retry(folder, stage, "service_unavailable")
            store.write(marker, b"")
        state = store.read(folder, "state.json")
        if state["stage"] == stage and state["status"] != "completed":
            if next_stage:
                store.save(folder, "state.json", dict(status="queued", stage=next_stage))
            else:
                store.save(folder, "state.json", dict(status="completed", stage=stage,
                                                   model=store.read(folder, "model.json")))
        if next_stage and not (folder / f"{stage}.sent").exists():
            send(next_stage, job)
            store.write(folder / f"{stage}.sent", b"")


def retry(folder, stage, code):
    count_file = stage + ".attempts"
    count = store.read(folder, count_file) + 1 if (folder / count_file).exists() else 1
    store.save(folder, count_file, count)
    store.save(folder, "state.json", dict(status="failed" if count >= 3 else "waiting",
                                         stage=stage, code=code, attempts=count))
    return "retry" if count < 3 else None


def consume(stage):
    with broker.channel() as ch, httpx.Client(timeout=300, trust_env=False) as client:
        while True:
            if stage == "generation":
                if client.get("http://generation:8000/ready").status_code != 200:
                    time.sleep(2)
                    continue
            method, _, body = ch.basic_get(stage, auto_ack=False)
            if not method:
                time.sleep(0.5)
                continue
            try:
                job = UUID(body.decode("ascii"))
            except (UnicodeError, ValueError):
                ch.basic_reject(method.delivery_tag, requeue=False)
                continue
            if not (store.directory(job) / "request.json").is_file():
                ch.basic_reject(method.delivery_tag, requeue=False)
                continue
            result = process(client, stage, job, lambda target, key: broker.publish(ch, target, key))
            if result == "retry":
                # Новая подтверждённая доставка не расходует лимит redelivery quorum-очереди.
                broker.publish(ch, stage, job)
                time.sleep(2)
            ch.basic_ack(method.delivery_tag)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=broker.STAGES)
    stage = parser.parse_args().stage
    while True:
        try:
            consume(stage)
        except (OSError, httpx.RequestError):
            logging.exception("Соединение недоступно")
        except Exception:
            logging.exception("Ошибка воркера")
        time.sleep(2)
