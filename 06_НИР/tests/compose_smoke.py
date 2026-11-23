"""Интеграционная проверка Compose без GPU. Запускать на чистых томах CI."""
import json
import subprocess
import time
from uuid import uuid4

import httpx


def compose(*args):
    return subprocess.check_output(["docker", "compose", *args], text=True)


def generation_depth():
    output = compose("exec", "-T", "rabbitmq", "rabbitmqctl", "-q", "list_queues",
                     "name", "messages_ready", "--formatter", "json")
    return next((r["messages_ready"] for r in json.loads(output) if r["name"] == "generation"), 0)


def wait_for(check):
    for _ in range(90):
        if check():
            return
        time.sleep(2)
    raise TimeoutError("Истекло время ожидания очереди")


if __name__ == "__main__":
    with httpx.Client(base_url="http://127.0.0.1:8010", timeout=20, trust_env=False) as client:
        keys = [str(uuid4()), str(uuid4())]
        for key in keys:
            for _ in range(2):
                response = client.post("/jobs", json={"prompt": "stone"}, headers={"Idempotency-Key": key})
                response.raise_for_status()
                assert response.json()["job_id"] == key
        wait_for(lambda: generation_depth() == 2)
        compose("restart", "rabbitmq")
        compose("up", "-d", "--wait", "rabbitmq")
        wait_for(lambda: generation_depth() == 2)
        for key in keys:
            assert client.get(f"/jobs/{key}").json() == {"status": "queued", "stage": "generation"}
