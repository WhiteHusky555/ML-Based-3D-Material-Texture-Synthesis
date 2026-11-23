"""Запуск локального конвейера и сохранение карт в новый каталог."""
import argparse
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx


def run(prompt, seed, noise_seed, output, upscale=False):
    if output.exists():
        raise FileExistsError(output)
    with httpx.Client(timeout=300, trust_env=False) as client:
        def post(port, route, body):
            response = client.post(f"http://127.0.0.1:{port}/{route}", json=body)
            response.raise_for_status()
            return response.json()

        height = post(8011, "noise", {"seed": noise_seed})["height"]
        generated = post(8012, "generate", dict(height=height, prompt=prompt, seed=seed, upscale=upscale))
        maps = post(8013, "pbr", dict(height=height, albedo=generated["albedo"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "result"
        stage.mkdir()
        for name in ("height", "normal", "roughness", "ao", "albedo"):
            value = generated[name] if name == "albedo" else maps[name]
            (stage / f"{name}.png").write_bytes(base64.b64decode(value, validate=True))
        manifest = dict(prompt=prompt, seed=seed, noise_seed=noise_seed, upscale=upscale, model=generated["model"])
        (stage / "run.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
        stage.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--noise-seed", type=int, default=42)
    parser.add_argument("--upscale", action="store_true")
    options = parser.parse_args()
    run(**vars(options))
