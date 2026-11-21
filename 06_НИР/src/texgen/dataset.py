"""Подготовка выборки Color по проверенному каталогу материалов ambientCG."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image


def prepare(catalog, output, limit=400, seed=42):
    """Одна строка CSV описывает один материал и его исходную карту Color."""
    if output.exists() or limit < 1:
        raise ValueError("Нужен новый выходной каталог и положительный размер выборки")
    fields = {"material_id", "group_id", "category", "license", "source_url", "color", "caption"}
    rows, ids, images, groups = [], set(), {}, {}
    root = catalog.resolve().parent
    with catalog.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if set(reader.fieldnames or []) != fields:
            raise ValueError(f"Ожидаются колонки: {sorted(fields)}")
        for raw in reader:
            if None in raw or any(not v or not v.strip() for v in raw.values()):
                raise ValueError(f"Неполная запись в строке {reader.line_num}")
            r = {k: v.strip() for k, v in raw.items()}
            if r["license"] != "CC0":
                continue
            mid, group, cat = r["material_id"], r["group_id"], r["category"]
            if not mid.isascii() or not mid.isalnum() or mid.casefold() in ids:
                raise ValueError(f"Недопустимый или повторный material_id: {mid}")
            if r["source_url"] != f"https://ambientcg.com/view?id={mid}":
                raise ValueError(f"Проверьте ссылку на материал {mid}")
            path = (root / r["color"]).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError(f"Не найдена локальная карта Color для {mid}")
            with Image.open(path) as im:
                if im.mode != "RGB" or im.width != im.height or im.width < 512:
                    raise ValueError(f"{mid}: нужна квадратная RGB-карта от 512 пикселей")
                digest = hashlib.sha256(im.tobytes()).hexdigest()
            if digest in images:
                raise ValueError(f"Совпадают карты {mid} и {images[digest]}")
            images[digest] = mid
            ids.add(mid.casefold())
            if groups.setdefault(group, cat) != cat:
                raise ValueError(f"Группа {group} отнесена к разным категориям")
            rows.append(dict(r, sha256_rgb=digest))
    if len(rows) < limit:
        raise ValueError(f"Доступно {len(rows)} материалов CC0, запрошено {limit}")

    def order(key):
        return hashlib.sha256(f"{seed}/{key}".encode()).digest()

    # Берём по одному материалу каждой категории за проход.
    buckets = {}
    for r in sorted(rows, key=lambda r: order(r["material_id"])):
        buckets.setdefault(r["category"], []).append(r)
    selected = []
    for index in range(max(map(len, buckets.values()))):
        for cat in sorted(buckets):
            if index < len(buckets[cat]):
                selected.append(buckets[cat][index])
        if len(selected) >= limit:
            break
    selected = selected[:limit]
    splits = {}
    for cat in sorted({r["category"] for r in selected}):
        keys = sorted({r["group_id"] for r in selected if r["category"] == cat}, key=order)
        if len(keys) < 3:
            raise ValueError(f"{cat}: нужно хотя бы три независимые группы")
        n = max(1, round(len(keys) / 10))
        for i, key in enumerate(keys):
            splits[key] = "test" if i < n else "validation" if i < 2*n else "train"

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "dataset"
        stage.mkdir()
        with (stage / "manifest.jsonl").open("w", encoding="utf-8") as stream:
            for r in selected:
                dest = Path(splits[r["group_id"]]) / (r["material_id"] + ".png")
                (stage / dest).parent.mkdir(exist_ok=True)
                with Image.open(root / r["color"]) as im:
                    im.resize((512, 512), Image.Resampling.LANCZOS).save(stage / dest)
                print(json.dumps(dict(r, color=dest.as_posix(), split=dest.parts[0]),
                                 ensure_ascii=False), file=stream)
        stage.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    prepare(args.catalog, args.output, args.limit, args.seed)
