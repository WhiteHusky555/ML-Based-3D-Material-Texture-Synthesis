import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient

from texgen.jobs import api, store, worker


class JobsTest(unittest.TestCase):
    def test_recovery_and_duplicate_delivery(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(store, "ROOT", Path(tmp)), \
                patch.object(api.broker, "channel"), patch.object(api.broker, "publish") as publish:
            client = TestClient(api.app)
            jobs = [uuid4(), uuid4()]
            for job in jobs:
                headers = {"Idempotency-Key": str(job)}
                for _ in range(2):
                    self.assertEqual(client.post("/jobs", headers=headers, json={"prompt":"stone"}).status_code, 202)
                self.assertEqual(client.post("/jobs", headers=headers, json={"prompt":"wood"}).status_code, 409)
            self.assertEqual(publish.call_count, 2)

            def compute(client, stage, folder, params):
                if stage == "generation":
                    store.save(folder, "model.json", {"version": "test"})

            def offline(stage, job):
                raise ConnectionError("broker down")

            with patch.object(worker, "compute", side_effect=compute) as calculation:
                with self.assertRaises(ConnectionError):
                    worker.process(None, "noise", jobs[0], offline)
                for job in jobs:
                    worker.process(None, "noise", job, publish)
                    state = client.get(f"/jobs/{job}").json()
                    self.assertEqual(state, {"status":"queued", "stage":"generation"})
                for job in jobs:
                    for stage in ("generation", "pbr", "noise", "generation", "pbr"):
                        worker.process(None, stage, job, publish)
                    self.assertEqual(client.get(f"/jobs/{job}").json()["status"], "completed")
                self.assertEqual(calculation.call_count, 6)
