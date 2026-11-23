import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from texgen.generation.api import app as generation, registry
from texgen.http_maps import encode
from texgen.noise.api import app as noise
from texgen.pbr.api import app as pbr


class ErrorsTest(unittest.TestCase):
    def test_noise_validation_and_routing(self):
        client = TestClient(noise)
        response = client.post("/noise", json={"size": -1})
        self.assertEqual(response.status_code, 422)
        error = response.json()["error"]
        self.assertEqual((error["service"], error["code"]), ("noise", "invalid_request"))
        self.assertEqual(error["fields"][0]["location"], ["body", "size"])
        self.assertEqual(client.get("/unknown").json()["error"]["code"], "not_found")
        response = client.get("/noise")
        self.assertEqual(response.json()["error"]["code"], "method_not_allowed")
        self.assertIn("POST", response.headers["Allow"])

    def test_map_errors(self):
        client = TestClient(pbr)
        for data, code in [("!", "invalid_base64"), ("YWJj", "invalid_png"),
                           (encode(Image.new("L", (8, 8))), "unsupported_map")]:
            with self.subTest(code=code):
                response = client.post("/pbr", json={"height": data, "albedo": data})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"]["code"], code)

    def test_model_states(self):
        client = TestClient(generation)
        payload = {"height": "AA==", "prompt": "stone", "seed": 1}
        with patch.object(registry, "provider", None):
            self.assertEqual(client.get("/ready").json()["error"]["code"], "model_unavailable")
        with registry.lock:
            response = client.post("/generate", json=payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "model_busy")
        self.assertEqual(response.headers["Retry-After"], "1")

    def test_internal_error(self):
        with patch("texgen.noise.api.generate", side_effect=RuntimeError("test failure")), self.assertLogs("texgen.errors") as logs:
            response = TestClient(noise, raise_server_exceptions=False).post("/noise", json={})
        self.assertEqual(response.status_code, 500)
        error = response.json()["error"]
        self.assertEqual(error["code"], "internal_error")
        self.assertIn(error["incident_id"], logs.output[0])
        self.assertNotIn("test failure", response.text)
