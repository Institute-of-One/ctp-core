# -*- coding: utf-8 -*-
"""Gamma-variate fitting, peak detection and derived indices, synthetic data only."""

import _pathfix  # noqa: F401
import numpy as np

from ctp_core.gamma_fit import (
    gamma_variate, fit_gamma_variate, compute_raw_indices,
)
from ctp_core.synthetic import generate_synthetic_tac


def test_gamma_variate_curve_generation():
    """gamma_variate is zero before t0, unimodal and finite."""
    t = np.linspace(0, 40, 41)
    y = gamma_variate(t, K=10.0, t0=8.0, alpha=3.0, beta=2.0)
    assert np.all(np.isfinite(y))
    assert np.allclose(y[t <= 8.0], 0.0)
    assert y.max() > 0
    # Unimodal: monotonic either side of the peak
    pk = int(np.argmax(y))
    assert np.all(np.diff(y[:pk + 1]) >= -1e-9)
    assert np.all(np.diff(y[pk:]) <= 1e-9)


def test_fit_returns_finite_parameters():
    """Fitting a noiseless curve returns finite parameters."""
    tac = generate_synthetic_tac(noise_std=0.0, seed=0)
    r = fit_gamma_variate(tac.time, tac.clean)
    assert r.success
    for p in (r.K, r.t0, r.alpha, r.beta):
        assert np.isfinite(p)


def test_fit_recovers_ground_truth_noiseless():
    """Without noise the true values are recovered accurately."""
    tac = generate_synthetic_tac(amplitude=60, t0=8, alpha=3, beta=2,
                                 noise_std=0.0, seed=0)
    r = fit_gamma_variate(tac.time, tac.clean)
    assert r.success
    assert abs(r.peak_time - tac.ground_truth["true_peak_time"]) < 0.5
    assert r.r_squared > 0.99


def test_fit_robust_to_moderate_noise():
    tac = generate_synthetic_tac(amplitude=60, snr=20, seed=0)
    r = fit_gamma_variate(tac.time, tac.noisy)
    assert r.success
    assert np.isfinite(r.peak_time) and np.isfinite(r.peak_value)
    # Even with moderate noise, peak_time should be within about +/- 2 s
    assert abs(r.peak_time - tac.ground_truth["true_peak_time"]) < 2.0


def test_peak_detection_plausible_location():
    """Raw peak detection returns a value near the true peak_time."""
    tac = generate_synthetic_tac(amplitude=60, t0=8, alpha=3, beta=2,
                                 snr=30, seed=0)
    raw = compute_raw_indices(tac.time, tac.noisy)
    true_ttp = tac.ground_truth["true_peak_time"]
    assert abs(raw["ttp"] - true_ttp) <= 2.0
    assert raw["peak"] > 0


def test_derived_parameters_finite():
    tac = generate_synthetic_tac(snr=20, seed=0)
    r = fit_gamma_variate(tac.time, tac.noisy)
    for v in (r.peak_value, r.peak_time, r.auc, r.bat, r.rmse, r.r_squared):
        assert np.isfinite(v)


def test_fit_failure_returns_result_not_exception():
    """An all-zero curve returns success=False instead of raising -- never fail silently."""
    t = np.linspace(0, 40, 41)
    r = fit_gamma_variate(t, np.zeros_like(t))
    assert r.success is False
    assert r.error_message != ""


def test_raw_indices_keys():
    tac = generate_synthetic_tac(seed=0)
    raw = compute_raw_indices(tac.time, tac.noisy)
    assert set(raw.keys()) == {"ttp", "peak", "auc", "bat"}


if __name__ == "__main__":
    import _runner
    _runner.run(globals())
