"""Подготовка слепого парного просмотра и подсчёт предпочтений."""
import argparse
import csv
import json
from collections import Counter
from html import escape
from pathlib import Path
from random import SystemRandom
from tempfile import TemporaryDirectory

from PIL import Image


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def prepare(images, output):
    protocol = json.loads((Path(__file__).resolve().parents[1] / "data/controlnet-validation/protocol.json").read_text(encoding="utf8"))
    cases = [(s, c["seed"], d) for s in protocol["samples"] for c in protocol["conditions"]
             for d in protocol["diffusion_seeds"]]
    rng = SystemRandom()
    rng.shuffle(cases)
    sides = ["left", "right"] * (len(cases) // 2)
    rng.shuffle(sides)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(exist_ok=True, parents=True)
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "session"
        public = stage / "review"
        public.mkdir(parents=True)
        key, votes, sections = [], [], []
        for i, ((sample, noise, diffusion), lora_side) in enumerate(zip(cases, sides, strict=True), 1):
            pair = f"P{i:02d}"
            mid = sample["material_id"]
            for side in ("left", "right"):
                model = "lora" if side == lora_side else "base"
                source = images / model / f"{mid}_{noise}_{diffusion}.png"
                with Image.open(source, formats=["PNG"]) as im:
                    if im.mode != "RGB" or im.size != (512, 512):
                        raise ValueError(f"Требуется RGB 512×512: {source}")
                    # Переносим только пиксели, без имён моделей и метаданных PNG.
                    Image.frombytes("RGB", im.size, im.tobytes()).save(public / f"{pair}_{side}.png")
            key.append(dict(pair=pair, material_id=mid, noise_seed=noise, diffusion_seed=diffusion, lora_side=lora_side))
            votes.append(dict(pair=pair, preference="", defects_left="", defects_right=""))
            sections.append(f"<h2>{pair}</h2><p>{escape(sample['caption'])}</p><div>"
                            f'<img alt="Слева" src="{pair}_left.png"><img alt="Справа" src="{pair}_right.png"></div>')
        write_csv(stage / "key.csv", key)
        write_csv(public / "votes.csv", votes)
        (public / "index.html").write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Парная оценка</title>'
            '<style>body{max-width:1050px;margin:auto;font:17px system-ui}div{display:flex;gap:1%}img{width:49%;height:auto}</style>'
            '<h1>Соответствие описанию</h1><p>В votes.csv укажите left, right или tie. В двух последних колонках запишите дефекты соответствующей плитки.</p>'
            + "".join(sections) + "</html>", encoding="utf8")
        stage.rename(output)


def score(session):
    def load(path):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        indexed = {r["pair"]: r for r in rows}
        if len(indexed) != len(rows) or not rows:
            raise ValueError("Пустой протокол или повтор номера пары")
        return indexed

    key, votes = load(session / "key.csv"), load(session / "review/votes.csv")
    if key.keys() != votes.keys():
        raise ValueError("Номера пар не совпадают с ключом")
    counts = Counter()
    by_material = {}
    for pair, item in key.items():
        vote = votes[pair]["preference"].strip().lower()
        if vote not in ("left", "right", "tie"):
            raise ValueError(f"Проверьте оценку {pair}")
        outcome = "tie" if vote == "tie" else "lora" if vote == item["lora_side"] else "base"
        counts[outcome] += 1
        by_material.setdefault(item["material_id"], Counter())[outcome] += 1
    return dict(pairs=len(key), materials=len(by_material), totals=counts, by_material=by_material)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("prepare")
    build.add_argument("images", type=Path)
    build.add_argument("session", type=Path)
    actions.add_parser("score").add_argument("session", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.images, args.session)
    else:
        print(json.dumps(score(args.session), indent=2))
