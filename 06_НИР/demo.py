"""Запуск и демонстрация локального стенда texgen-nir."""
import argparse
import base64
import getpass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import html
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
import zlib

ROOT = Path(__file__).resolve().parent
# Все запросы идут только на фиксированные порты localhost.
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))
API = "http://127.0.0.1:8010/jobs"
PNG = b"\x89PNG\r\n\x1a\n"


def request(url, body=None, headers=None, raw=False, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with LOCAL.open(req, timeout=timeout) as response:
        data = response.read()
    return data if raw else json.loads(data)


def docker(*args, capture=False, env=None):
    return subprocess.run(["docker", *args], cwd=ROOT, env=env, check=True,
                          stdout=subprocess.PIPE if capture else None,
                          text=True, errors="replace").stdout


def control_albedo(size):
    """Однотонная контрольная RGB-карта для проверки PBR без весов."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    header = struct.pack(">2I5B", size, size, 8, 2, 0, 0, 0)
    pixels = (b"\0" + bytes((130, 114, 96)) * size) * size
    return PNG + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


def demo(args, folder, note, cards):
    if not shutil.which("docker"):
        raise RuntimeError("Docker CLI не найден.")
    try:
        docker("info", "--format", "{{.ServerVersion}}", capture=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Docker Engine недоступен. Запустите Docker Desktop в режиме Linux containers.") from exc

    if args.start or args.gpu:
        env = os.environ.copy()
        if not env.get("AMQP_USER"):
            env["AMQP_USER"] = input("Пользователь RabbitMQ: ").strip()
        if not env.get("AMQP_PASSWORD"):
            env["AMQP_PASSWORD"] = getpass.getpass("Пароль RabbitMQ (для существующего тома — прежний): ")
        files = ["-f", "compose.yaml"]
        if args.gpu:
            files += ["-f", "compose.gpu.yaml"]
        docker("compose", *files, "up", "--build", "-d", "--wait", env=env)
    containers = docker("ps", "-a", "--filter", "label=com.docker.compose.project=texgen-nir",
                        "--format", "{{.Names}}  {{.Status}}", capture=True).strip()
    if not containers:
        raise RuntimeError("Контейнеры texgen-nir не найдены. Запустите скрипт с --start.")
    note(containers)
    deadline = time.monotonic() + 60
    for port in range(8010, 8014):
        while True:
            try:
                request(f"http://127.0.0.1:{port}/openapi.json", timeout=3)
                break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"API на порту {port} недоступен.")
                time.sleep(1)

    def save(name, data):
        if not data.startswith(PNG) or len(data) < 24:
            raise ValueError(f"Некорректная PNG-карта: {name}")
        (folder / f"{name}.png").write_bytes(data)
        cards.append(name)

    without_model = False
    try:
        ready = request("http://127.0.0.1:8012/ready")
        note(f"Активная модель: {ready['model']['version']}")
    except urllib.error.HTTPError as exc:
        if exc.code != 503 or json.load(exc).get("error", {}).get("code") != "model_unavailable":
            raise
        without_model = True
        note("Модель ещё не подключена.")

    key = str(uuid.uuid4())
    note(f"Задание: {API}/{key}")
    job = request(API, {"prompt": "rough asphalt", "noise_seed": 12, "seed": 42},
                  {"Idempotency-Key": key})
    url = f"{API}/{uuid.UUID(job['job_id'])}"
    deadline = time.monotonic() + args.timeout
    previous = None
    while True:
        state = request(url)
        current = (state["stage"], state["status"])
        if current != previous:
            note(" / ".join(current))
            previous = current
        if state["status"] == "failed":
            raise RuntimeError(f"Ошибка этапа {state['stage']}: {state.get('code')}")
        if state["status"] == "completed":
            note(f"Готовый материал. Версия модели: {state['model']['version']}")
            for name in ("albedo", "height", "normal", "roughness", "ao"):
                save(name, request(f"{url}/maps/{name}", raw=True))
            break
        if without_model and state["stage"] == "generation":
            note("Шум обработан. Задание осталось в очереди генерации. "
                 "Ниже — отдельная проверка PBR на контрольной albedo.")
            noise = request("http://127.0.0.1:8011/noise", {"size": 128, "cells": 4, "seed": 12})
            save("noise", base64.b64decode(noise["height"], validate=True))
            color = control_albedo(128)
            save("control-albedo", color)
            maps = request("http://127.0.0.1:8013/pbr", {"height": noise["height"],
                           "albedo": base64.b64encode(color).decode()})
            for name in ("height", "normal", "roughness", "ao"):
                save("pbr-" + name, base64.b64decode(maps[name], validate=True))
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Истекло время ожидания. Задание можно проверить по адресу {url}")
        time.sleep(2)


def page(messages, cards, status, live=False):
    labels = {"noise": "Шум", "albedo": "Albedo", "control-albedo": "Контрольная albedo",
              "height": "Высота", "normal": "Нормали", "roughness": "Шероховатость", "ao": "Окклюзия"}
    figures = "".join(
        f'<a href="{name}.png" target="_blank" rel="noopener"><img src="{name}.png" alt="{name}">'
        f'<span>{labels[name.removeprefix("pbr-")]}</span></a>' for name in cards)
    refresh = '<meta http-equiv="refresh" content="2">' if live and status == "running" else ""
    title = {"running": "Идёт проверка", "done": "Проверка завершена", "error": "Проверка остановлена"}[status]
    log = html.escape("\n".join(messages))
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
{refresh}<title>Texgen · Демонстрация</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#121817;color:#ecf0e8;font:16px/1.5 Inter,system-ui,sans-serif}}
main{{max-width:1080px;margin:auto;padding:clamp(18px,5vw,68px)}}header{{border-bottom:1px solid #43504b;padding-bottom:20px}}
h1{{font-size:clamp(28px,6vw,56px);letter-spacing:-.045em;margin:0}}h2{{font-size:20px;margin-top:32px}}
.status{{color:#a6e5bd}}.error{{color:#ffbaaa}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#1c2522;
border-left:3px solid #648775;padding:18px;color:#d3ded7;font:14px/1.7 ui-monospace,monospace}}
section{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(210px,100%),1fr));gap:16px}}
a{{display:block;background:#23302a;color:inherit;text-decoration:none;border-radius:8px;overflow:hidden}}
a:hover,a:focus-visible{{outline:2px solid #a6e5bd}}img{{display:block;width:100%;aspect-ratio:1;object-fit:contain}}
a span{{display:block;padding:10px 14px}}
</style><main><header><h1>Генерация материала</h1><div class="status {status}">{title}</div></header>
<h2>Ход проверки</h2><pre>{log or "Подключение к стенду…"}</pre>
{'<h2>Карты материала</h2><section>'+figures+'</section>' if cards else ''}</main></html>"""


def dashboard(folder, messages, cards, state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                data = page(messages.copy(), cards.copy(), state["status"], live=True).encode()
                mime = "text/html; charset=utf-8"
            elif self.path in {f"/{name}.png" for name in cards.copy()}:
                data = (folder / self.path[1:]).read_bytes()
                mime = "image/png"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", action="store_true", help="показать ход проверки в браузере")
    parser.add_argument("--start", action="store_true", help="собрать и запустить Compose")
    parser.add_argument("--gpu", action="store_true", help="запустить Compose с GPU-конфигурацией")
    parser.add_argument("--no-open", action="store_true", help="сохранить отчёт без открытия браузера")
    parser.add_argument("--timeout", type=int, default=300, help="ожидание задания в секундах")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout должен быть положительным")
    folder = Path(tempfile.mkdtemp(prefix="texgen-demo-"))
    messages, cards = [], []

    def note(message):
        print(message, flush=True)
        messages.append(message)

    state = {"status": "running"}
    server = dashboard(folder, messages, cards, state) if args.web else None
    if server:
        url = f"http://127.0.0.1:{server.server_port}/"
        Thread(target=server.serve_forever, daemon=True).start()
        print(f"Демонстрация: {url}", flush=True)
        if not args.no_open:
            webbrowser.open(url)

    code = 0
    try:
        demo(args, folder, note, cards)
        state["status"] = "done"
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        note(f"Ошибка: {exc}")
        state["status"] = "error"
        code = 1
    report = folder / "index.html"
    report.write_text(page(messages, cards, state["status"]), encoding="utf8")
    print(f"Отчёт: {report}", flush=True)
    if server:
        try:
            print("Для закрытия демо нажмите Ctrl+C.", flush=True)
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
    elif not args.no_open:
        webbrowser.open(report.as_uri())
    return code


if __name__ == "__main__":
    sys.exit(main())
