"""Проверка подготовки выборки на синтетических картах."""
import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from texgen.dataset import prepare


class DatasetTest(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.catalog = self.root / "catalog.csv"
        self.rows = []
        for i, group in enumerate(("A", "A", "B", "C", "D")):
            mid = f"Wood{i}"
            color = f"{mid}.png"
            Image.new("RGB", (640, 640), (i, 42, 80)).save(self.root / color)
            self.rows.append(dict(material_id=mid, group_id=group, category="Wood",
                                  license="CC0" if i < 4 else "other",
                                  source_url=f"https://ambientcg.com/view?id={mid}",
                                  color=color, caption="wood surface"))

    def write_catalog(self):
        with self.catalog.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.rows[0])
            writer.writeheader()
            writer.writerows(self.rows)

    def test_group_split_and_reproducibility(self):
        manifests = []
        for name in ("first", "second"):
            self.write_catalog()
            output = self.root / name
            prepare(self.catalog, output, limit=4)
            records = [json.loads(line) for line in
                       (output / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
            manifests.append(records)
            self.assertEqual({r["material_id"] for r in records}, {f"Wood{i}" for i in range(4)})
            self.assertEqual({r["split"] for r in records}, {"train", "validation", "test"})
            self.assertEqual(len({r["split"] for r in records if r["group_id"] == "A"}), 1)
            for record in records:
                with Image.open(output / record["color"]) as im:
                    self.assertEqual((im.mode, im.size), ("RGB", (512, 512)))
            self.rows.reverse()
        self.assertEqual(*manifests)

    def test_limit_preserves_independent_groups(self):
        self.write_catalog()
        output = self.root / "subset"
        prepare(self.catalog, output, limit=3)
        records = [json.loads(line) for line in
                   (output / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual({r["group_id"] for r in records}, {"A", "B", "C"})
        self.assertEqual({r["split"] for r in records}, {"train", "validation", "test"})

    def test_grayscale_export_and_luma_flag(self):
        flat = Image.new("L", (512, 512), 28)
        flat.putpixel((0, 0), 29)
        flat.save(self.root / "Wood0.png")
        flat.paste(64, (0, 0, 256, 512))
        flat.save(self.root / "Wood1.png")
        self.write_catalog()
        output = self.root / "dataset"
        prepare(self.catalog, output, limit=4)
        records = {r["material_id"]: r for r in map(json.loads,
                   (output / "manifest.jsonl").read_text(encoding="utf-8").splitlines())}
        self.assertTrue(records["Wood0"]["nearly_uniform_luma"])
        self.assertFalse(records["Wood1"]["nearly_uniform_luma"])
        self.assertEqual(records["Wood0"]["source_mode"], "L")
        with Image.open(output / records["Wood0"]["color"]) as im:
            self.assertEqual(im.mode, "RGB")
            self.assertEqual(im.getpixel((0, 0)), (29, 29, 29))
            self.assertEqual(im.getpixel((1, 0)), (28, 28, 28))

    def test_duplicate_pixels_rejected(self):
        gray = Image.new("L", (640, 640), 28)
        gray.save(self.root / "Wood0.png")
        gray.convert("RGB").save(self.root / "Wood1.png")
        self.write_catalog()
        output = self.root / "dataset"
        with self.assertRaisesRegex(ValueError, "Совпадают карты"):
            prepare(self.catalog, output, limit=4)
        self.assertFalse(output.exists())
