import unittest

import numpy as np
from PIL import Image

from texgen.metrics import cell_edges, measure


class TextureMetricsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.edges = cell_edges(128, 4, 12)

    def test_ramp_and_flat_axis(self):
        tile = np.tile(np.arange(128, dtype="uint8"), (128, 1))
        result = measure(Image.fromarray(tile), self.edges)
        self.assertEqual(result["x"], dict(seam=127, inside=1, ratio=127))
        self.assertEqual(result["y"], dict(seam=0, inside=0, ratio=None))

    def test_flat_image_has_no_edges(self):
        result = measure(Image.new("RGB", (128, 128), "gray"), self.edges)
        for key in ("edge_density", "coverage", "shifted_coverage", "coverage_gain"):
            self.assertEqual(result[key], 0)

    def test_contours_beat_shifted_control(self):
        edges = cell_edges(512, 8, 12)
        image = Image.fromarray(edges.astype("uint8") * 255)
        result = measure(image, edges)
        self.assertGreater(result["coverage"], .95)
        self.assertGreater(result["coverage_gain"], .25)
