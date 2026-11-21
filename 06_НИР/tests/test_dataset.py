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

    def test_duplicate_pixels_rejected(self):
        self.rows[1]["color"] = self.rows[0]["color"]
        self.write_catalog()
        output = self.root / "dataset"
        with self.assertRaisesRegex(ValueError, "Совпадают карты"):
            prepare(self.catalog, output, limit=4)
        self.assertFalse(output.exists())
