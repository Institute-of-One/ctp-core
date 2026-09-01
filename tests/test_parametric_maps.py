# -*- coding: utf-8 -*-
"""Parametric map generation (ctp_core.parametric_maps), synthetic data only.

This module produced the CBF/CBV/MTT/TTP maps shown in the software paper but had no
tests, and that gap hid a real defect: ``np.trapz`` was removed in NumPy 2.0, so the
CBV path raised ``AttributeError`` on any current install. The tests below exercise the
integral rather than only importing the module, so the same class of breakage fails here
first.
"""

import re
from pathlib import Path

import _pathfix  # noqa: F401
import numpy as np

import ctp_core
from ctp_core.parametric_maps import ParametricMapGenerator
from ctp_core.synthetic import generate_synthetic_tac


#: Attributes removed in NumPy 2.0. ``np.trapz`` is the one that actually broke; the rest
#: are here so the whole class is guarded, not just the instance that was found.
NUMPY2_REMOVED = (
    "trapz", "alltrue", "sometrue", "product", "cumproduct", "round_", "float_",
    "complex_", "unicode_", "string_", "NaN", "NAN", "Inf", "Infinity", "infty",
    "NINF", "PINF", "issctype", "asfarray", "in1d", "row_stack", "safe_eval",
    "int0", "uint0", "bool8", "object0", "str0", "void0", "find_common_type", "msort",
)


#: CBV is clipped to [0, 20] and CBF to [0, 150] inside ``compute``. The tissue scales
#: below keep CBV in the linear range -- CBV = (tissue_area / aif_area) / 1.04 * 100, so
#: a scale of s gives 96.15 * s -- while keeping the peak tissue enhancement above the 5 HU
#: threshold that decides which pixels are processed at all. With amplitude 200 HU,
#: s = 0.05 gives a 10 HU peak and CBV 4.8, and s = 0.10 gives 20 HU and CBV 9.6.
AMPLITUDE = 200.0
SCALE_LOW = 0.05
SCALE_HIGH = 0.10


def _phantom(tissue_scale=SCALE_LOW, rows=6, cols=6, n_time_points=24, dt=2.0):
    """A 4D volume whose every masked pixel is a scaled copy of one clean AIF.

    Scaling the tissue curve by a known factor makes CBV analytically predictable, which
    is what lets the test check the integral instead of merely checking for finiteness.
    """
    tac = generate_synthetic_tac(amplitude=AMPLITUDE, n_time_points=n_time_points,
                                 dt=dt, snr=None, seed=0)
    time = np.asarray(tac.time, dtype=float)
    aif = np.asarray(tac.clean, dtype=float)
    volume = np.full((len(time), 1, rows, cols), 40.0)
    volume[:, 0] += (aif * tissue_scale)[:, None, None]
    metadata = {
        "n_times": len(time),
        "rows": rows,
        "cols": cols,
        "n_slices": 1,
        "time_seconds": [float(v) for v in time],
    }
    return volume, metadata, aif


def _compute(tissue_scale=SCALE_LOW):
    volume, metadata, aif = _phantom(tissue_scale=tissue_scale)
    maps = ParametricMapGenerator(volume, metadata).compute(
        aif, slice_index=0, n_baseline=2, method="circulant", svd_threshold=0.15
    )
    return maps


def test_compute_returns_finite_maps():
    maps = _compute()
    for name in ("cbf", "cbv", "mtt", "ttp", "tmax"):
        data = getattr(maps, name)
        assert data is not None, f"{name} was not produced"
        assert data.shape == (6, 6)
        assert np.all(np.isfinite(data)), f"{name} contains non-finite values"
        assert np.all(data >= 0), f"{name} contains negative values"


def test_every_masked_pixel_is_actually_processed():
    """``compute`` swallows per-pixel exceptions and leaves the pixel at zero.

    A failure inside the loop is therefore invisible in the maps themselves -- they just
    come back zero. Asserting the processed count against the total is what makes such a
    failure loud.
    """
    maps = _compute()
    info = maps.computation_info
    assert info["total_pixels"] == 36
    assert info["processed_pixels"] == info["total_pixels"], (
        "pixels were skipped by the bare `except Exception: continue`; "
        f"{info['processed_pixels']} of {info['total_pixels']} were processed"
    )
    assert info["aif_area"] > 0


def test_cbv_scales_with_the_tissue_curve_integral():
    """CBV is the tissue integral over the AIF integral, so doubling the tissue
    enhancement must double CBV. This exercises the trapezoidal integration that
    ``np.trapz`` used to perform, which is the call that NumPy 2.0 removed."""
    single = _compute(tissue_scale=SCALE_LOW)
    double = _compute(tissue_scale=SCALE_HIGH)
    a = float(np.mean(single.cbv))
    b = float(np.mean(double.cbv))
    assert a > 0, "CBV came back zero; the integral did not run"
    assert b < 20.0, "CBV hit the clip, so this test cannot see the scaling"
    expected = SCALE_HIGH / SCALE_LOW
    assert abs(b / a - expected) < 0.01, f"CBV did not scale with the integral: {a} -> {b}"
    # And the absolute value follows the documented definition, CBV = (A_t/A_a)/rho*100.
    assert abs(a - SCALE_LOW / 1.04 * 100.0) < 0.05


def test_ttp_is_the_sampled_maximum_time():
    volume, metadata, aif = _phantom()
    maps = ParametricMapGenerator(volume, metadata).compute(
        aif, slice_index=0, n_baseline=2, method="circulant", svd_threshold=0.15
    )
    time = np.asarray(metadata["time_seconds"], dtype=float)
    baseline = volume[:2, 0].mean(axis=0)
    expected = time[int(np.argmax((volume[:, 0] - baseline)[:, 0, 0]))]
    assert abs(float(maps.ttp[0, 0]) - float(expected)) < 1e-6


def test_invalid_aif_is_reported_not_silently_accepted():
    volume, metadata, _ = _phantom()
    flat = np.zeros(metadata["n_times"], dtype=float)
    generator = ParametricMapGenerator(volume, metadata)
    try:
        generator.compute(flat, slice_index=0, n_baseline=2)
    except ValueError:
        return
    raise AssertionError("a flat AIF must raise ValueError, not produce maps")


def test_package_uses_no_numpy_attribute_removed_in_numpy_2():
    """Guard the whole package, not just the site that was found.

    ``requirements-core.txt`` has no upper bound on NumPy, so a fresh install gets 2.x
    and any of these names raises AttributeError at run time.
    """
    root = Path(ctp_core.__file__).resolve().parent
    pattern = re.compile(r"\bnp\.(" + "|".join(NUMPY2_REMOVED) + r")\b")
    offenders = []
    for path in sorted(root.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # The compatibility shim names the removed attribute deliberately.
            if "hasattr(np, 'trapezoid')" in line or 'hasattr(np, "trapezoid")' in line:
                continue
            for match in pattern.finditer(line):
                offenders.append(f"{path.name}:{number} {match.group(0)}")
    assert not offenders, "NumPy 2.0 removed these: " + "; ".join(offenders)


def test_trapezoid_shim_is_a_trapezoidal_integral():
    """Compare the shim against a trapezoidal sum written out here, rather than against a
    constant typed into the test. The point is that the name resolves to the right
    function on both NumPy 1.x and 2.x, not how accurate NumPy is."""
    time = np.linspace(0.0, 10.0, 51)
    values = np.sin(time) ** 2
    trapezoid = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    by_hand = float(np.sum((values[:-1] + values[1:]) / 2.0 * np.diff(time)))
    assert abs(float(trapezoid(values, time)) - by_hand) < 1e-12


if __name__ == "__main__":
    import _runner
    _runner.run(globals())
