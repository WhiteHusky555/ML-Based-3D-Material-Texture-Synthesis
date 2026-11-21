import unittest
import numpy as np
from texgen.noise import generate, sample, _render


class NoiseTest(unittest.TestCase):
    def test_period_and_seed(self):
        x, y = np.random.default_rng(7).uniform(-1, 2, (2, 200))
        for kind in ("perlin", "voronoi"):
            expected = sample(kind, x, y)
            for dx, dy in [(1, 0), (0, -1), (-2, 3)]:
                np.testing.assert_allclose(sample(kind, x+dx, y+dy), expected, atol=1e-12, rtol=0)
            field = generate(kind, 64)
            axis = np.arange(64)/64
            np.testing.assert_allclose(field, sample(kind, axis[None,:], axis[:,None]), atol=1e-12)
            np.testing.assert_array_equal(generate(kind, 128)[::2, ::2], field)
            np.testing.assert_array_equal(generate(kind, 64), field)
            self.assertFalse(np.array_equal(generate(kind, 64, seed=43), field))
            self.assertTrue(np.all((field >= 0) & (field <= 1)))
            self.assertGreater(np.std(field), 0.01)

    def test_coursework_tiling(self):
        cells = 4
        angles = np.random.default_rng(7).uniform(0, 2*np.pi, (64,64))
        sites = np.random.default_rng(7).random((cells,cells,2))
        raw = _render(2, np.arange(128)/64, cells, np.cos(angles), np.sin(angles), sites)
        tile = generate("combined", 64, cells, 7)
        np.testing.assert_allclose(np.tile(tile, (2,2)), np.clip(0.5+0.5*raw,0,1), atol=1e-12)
        self.assertGreater(tile.std(), 0.01)
