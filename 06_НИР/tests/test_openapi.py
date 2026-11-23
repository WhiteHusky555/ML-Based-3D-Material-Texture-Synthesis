import unittest

from fastapi.testclient import TestClient

from texgen.generation.api import app as generation
from texgen.jobs.api import app as jobs
from texgen.noise.api import app as noise
from texgen.pbr.api import app as pbr


class OpenAPITest(unittest.TestCase):
    def test_documented_services(self):
        for app in (jobs, noise, generation, pbr):
            with self.subTest(service=app.title):
                client = TestClient(app)
                self.assertEqual(client.get("/docs").status_code, 200)
                paths = client.get("/openapi.json").json()["paths"]
                for operations in paths.values():
                    for operation in operations.values():
                        responses = operation["responses"]
                        success = responses.get("200") or responses["202"]
                        for media in success["content"].values():
                            self.assertTrue(media["schema"])
                        self.assertIn("500", responses)
                        for code, response in responses.items():
                            if code.startswith(("4", "5")):
                                schema = response["content"]["application/json"]["schema"]
                                self.assertEqual(schema["$ref"], "#/components/schemas/ErrorResponse")
                if app is jobs:
                    download = paths["/jobs/{job}/maps/{name}"]["get"]["responses"]["200"]
                    self.assertEqual(set(download["content"]), {"image/png"})
