from contextlib import asynccontextmanager
from threading import Event, Thread

from ..contracts import Generated, Ready, error
from ..errors import ServiceError, service_app
from PIL import Image
from pydantic import Field

from ..http_maps import Request, decode, encode
from .provider import load
from .registry import ROOT, Registry

registry = Registry(ROOT, load)


@asynccontextmanager
async def lifespan(app):
    stop = Event()

    def watch():
        while not stop.is_set():
            with registry.lock:
                registry.refresh()
            stop.wait(1)

    watcher = Thread(target=watch, daemon=True)
    watcher.start()
    try:
        yield
    finally:
        stop.set()
        watcher.join()


app = service_app("generation", title="Генерация", lifespan=lifespan)


class Generation(Request):
    prompt: str = Field(min_length=1, max_length=2048)
    height: str = Field(min_length=1, max_length=12000000)
    seed: int = Field(ge=0, le=2**32-1)
    upscale: bool = Field(False, description="Апскейл стенда: Lanczos, 512 → 1024. В целевой архитектуре — этап Real-ESRGAN.")


@app.get("/ready", summary="Проверить активную версию модели", response_model=Ready,
         responses={503: error("model_unavailable")})
def readiness():
    with registry.lock:
        if registry.provider is None:
            raise ServiceError(503, "model_unavailable", "Модель не готова.")
        return {"model": registry.current, "update_error": registry.error}


@app.post("/generate", summary="Сгенерировать карту albedo", response_model=Generated,
          responses={422: error("invalid_request, invalid_base64, invalid_png, unsupported_map"),
                     503: error("model_unavailable или model_busy (Retry-After в секундах)")})
def generate(params: Generation):
    if not registry.lock.acquire(blocking=False):
        raise ServiceError(503, "model_busy", "Генератор занят.", retry_after=1)
    try:
        if registry.provider is None:
            raise ServiceError(503, "model_unavailable", "Модель не готова.")
        height = decode(params.height, {"I;16", "L"})
        if height.mode == "I;16":
            height = height.convert("F").point(lambda x: x / 257).convert("L")
        control = height.resize((512, 512), Image.Resampling.BILINEAR).convert("RGB")
        albedo = registry.provider(params.prompt, control, params.seed)
        if params.upscale:
            albedo = albedo.resize((1024, 1024), Image.Resampling.LANCZOS)
        return {"albedo": encode(albedo), "model": registry.current}
    finally:
        registry.lock.release()
