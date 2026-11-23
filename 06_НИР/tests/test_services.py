import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from texgen.generation.api import app as generation
from texgen.generation.registry import Registry, publish
from texgen.http_maps import decode, encode
from texgen.noise.api import app as noise
from texgen.pbr.api import app as pbr


class ServicesTest(unittest.TestCase):
    def test_without_weights(self):
        height = TestClient(noise).post("/noise", json={"size": 32}).json()["height"]
        request = dict(height=height, seed=0, prompt="stone")
        self.assertEqual(TestClient(generation).post("/generate", json=request).status_code, 503)
        result = TestClient(pbr).post("/pbr", json=dict(height=height, albedo=encode(Image.new("RGB", (64, 64)))))
        self.assertEqual(result.status_code, 200)
        for value in result.json().values():
            self.assertEqual(decode(value, {"RGB", "L", "I;16"}).size, (64, 64))

    def test_model_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def load(path):
                if path.name == "broken":
                    raise ValueError("Ошибка проверки модели")
                return path.name

            registry = Registry(root, load)
            for revision, name, expected in [(1, "old", "old"), (2, "new", "new"),
                                             (3, "broken", "new"), (4, "old", "old")]:
                (root / name).mkdir(exist_ok=True)
                publish(root, revision, name)
                publish(root, revision, name)
                if name == "broken":
                    with self.assertLogs(level="ERROR"):
                        registry.refresh()
                else:
                    registry.refresh()
                self.assertEqual(registry.provider, expected)
                self.assertEqual(registry.current["version"], expected)
            restarted = Registry(root, load)
            restarted.refresh()
            self.assertEqual(restarted.provider, "old")
