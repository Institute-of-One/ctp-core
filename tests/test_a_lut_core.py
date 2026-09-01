# -*- coding: utf-8 -*-
"""Core checks on the ASIST a-LUT (ctp_core.a_lut).

Assuming the packaged LUT asset (ctp_core/assets/alut.csv) resolves safely through
importlib.resources, this confirms **deterministic RGB output** for a fixed scalar
input, and that the quantitative values are left unchanged.
"""

import _pathfix  # noqa: F401
import numpy as np

from ctp_core.a_lut import (
    load_a_lut, apply_a_lut, scalar_to_index, LUT_SIZE,
)


def test_packaged_lut_loads():
    lut = load_a_lut("asist")
    assert lut.shape == (LUT_SIZE, 3)
    assert lut.dtype == np.uint8
    assert tuple(lut[0]) == (0, 0, 0)       # low value = black
    assert tuple(lut[255]) == (255, 0, 0)   # high value = red


def test_deterministic_rgb_for_fixed_scalar():
    """A fixed scalar gives a bit-exact identical RGB: deterministic RGB output."""
    d = np.array([[0.0, 40.0, 80.0]])
    r1 = apply_a_lut(d, map_type="cbf")
    r2 = apply_a_lut(d, map_type="cbf")
    assert np.array_equal(r1, r2)


def test_fixed_scalar_exact_rgb_values():
    """With vmin=0 and vmax=80, values 0/40/80 give LUT indices 0/128/255."""
    lut = load_a_lut("asist")
    d = np.array([[0.0, 40.0, 80.0]])
    rgb = apply_a_lut(d, map_type="cbf")
    assert tuple(rgb[0, 0]) == tuple(lut[0])
    assert tuple(rgb[0, 1]) == tuple(lut[128])
    assert tuple(rgb[0, 2]) == tuple(lut[255])


def test_quantitative_values_unchanged():
    """Applying the LUT is display only: it does not modify the input array."""
    d = np.array([[10.0, 20.0], [30.0, 40.0]])
    snapshot = d.copy()
    _ = apply_a_lut(d, map_type="cbf")
    assert np.array_equal(d, snapshot)


def test_scalar_to_index_midpoint():
    assert scalar_to_index(np.array([40.0]), 0.0, 80.0)[0] == 128


if __name__ == "__main__":
    import _runner
    _runner.run(globals())
