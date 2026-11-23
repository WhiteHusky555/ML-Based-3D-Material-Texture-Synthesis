"""Средние парные разности LoRA − база по материалам из контрольной серии."""
import argparse
import csv
import json
import math
import sys
from pathlib import Path
from statistics import mean

METRICS = ("coverage_gain", "edge_density", "x_seam", "y_seam", "x_ratio", "y_ratio")


def summarize(series):
    protocol = json.loads((series / "run.json").read_text(encoding="utf8"))["protocol"]
    cases = [(sample["material_id"], condition["seed"], seed)
             for sample in protocol["samples"] for condition in protocol["conditions"]
             for seed in protocol["diffusion_seeds"]]
    expected = {(*case, model) for case in cases for model in ("base", "lora")}
    if not cases or len(expected) != 2 * len(cases):
        raise ValueError("Пустой протокол или повтор условий")
    values = {}
    with (series / "metrics.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["material_id"], int(row["noise_seed"]), int(row["diffusion_seed"]), row["model"])
            if key not in expected or key in values:
                raise ValueError(f"Лишняя или повторная строка: {key}")
            values[key] = {}
            for metric in METRICS:
                raw = row[metric]
                if raw == "" and metric in ("x_ratio", "y_ratio"):
                    values[key][metric] = None
                else:
                    value = float(raw)
                    if not math.isfinite(value):
                        raise ValueError(f"Неконечное значение {metric}: {key}")
                    values[key][metric] = value
    if values.keys() != expected:
        raise ValueError(f"Отсутствуют строки: {sorted(expected - values.keys())}")
    for sample in protocol["samples"]:
        material = sample["material_id"]
        for metric in METRICS:
            differences = []
            for case in cases:
                if case[0] == material:
                    a = values[(*case, "base")][metric]
                    b = values[(*case, "lora")][metric]
                    if a is not None and b is not None:
                        differences.append(b - a)
            yield material, metric, len(differences), mean(differences) if differences else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("series", type=Path)
    args = parser.parse_args()
    rows = list(summarize(args.series))
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(("material_id", "metric", "paired_n", "mean_lora_minus_base"))
    writer.writerows(rows)
