"""Проверка артефактов пилота перед переносом LoRA в сервис."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def verify(run, manifest):
    def load(name):
        return json.loads((run / name).read_text(encoding="utf8"))

    cfg = load("config.json")
    summary = load("summary.json")
    if cfg["manifest_sha256"] != hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise ValueError("Манифест пилота отличается от локального")
    with (run / "metrics.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if cfg["steps"] != 100 or summary["steps"] != 100 or [int(r["step"]) for r in rows] != list(range(1, 101)):
        raise ValueError("Журнал не содержит 100 последовательных обновлений")
    for row in rows:
        for field in ("loss", "seconds", "peak_mib", "lr"):
            if not math.isfinite(float(row[field])) or float(row[field]) < 0:
                raise ValueError(f"Некорректное значение {field} на шаге {row['step']}")
    adapter = run / "adapter/pytorch_lora_weights.safetensors"
    if adapter.stat().st_size != summary["adapter_bytes"] or adapter.stat().st_size == 0:
        raise ValueError("Размер адаптера расходится со сводкой пилота")
    for name in ("checkpoint.pt", "base.png", "lora.png", "comparison.jpg", "loss.png"):
        if not (run / name).stat().st_size:
            raise ValueError(f"Пустой файл {name}")
    with adapter.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(adapter_sha256=digest, base=cfg["base"], base_revision=cfg["base_rev"],
                controlnet=cfg["control"], controlnet_revision=cfg["control_rev"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    manifest = Path(__file__).resolve().parents[1] / "data/ambientcg-400.jsonl"
    print(json.dumps(verify(args.run, manifest), indent=2))
