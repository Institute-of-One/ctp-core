# -*- coding: utf-8 -*-
"""gamma-variate フィット・ピーク検出・派生指標の検証 (合成データのみ)。"""

import _pathfix  # noqa: F401
import numpy as np

from ctp_core.gamma_fit import (
    gamma_variate, fit_gamma_variate, compute_raw_indices,
)
from ctp_core.synthetic import generate_synthetic_tac


def test_gamma_variate_curve_generation():
    """gamma_variate は t0 以前ゼロ・単峰・有限。"""
    t = np.linspace(0, 40, 41)
    y = gamma_variate(t, K=10.0, t0=8.0, alpha=3.0, beta=2.0)
    assert np.all(np.isfinite(y))
    assert np.allclose(y[t <= 8.0], 0.0)
    assert y.max() > 0
    # 単峰: ピーク前後で単調
    pk = int(np.argmax(y))
    assert np.all(np.diff(y[:pk + 1]) >= -1e-9)
    assert np.all(np.diff(y[pk:]) <= 1e-9)


def test_fit_returns_finite_parameters():
    """ノイズ無し曲線へのフィットは有限パラメータを返す。"""
    tac = generate_synthetic_tac(noise_std=0.0, seed=0)
    r = fit_gamma_variate(tac.time, tac.clean)
    assert r.success
    for p in (r.K, r.t0, r.alpha, r.beta):
        assert np.isfinite(p)


def test_fit_recovers_ground_truth_noiseless():
    """ノイズ無しでは真値を高精度に回復する。"""
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
    # 中程度ノイズでも peak_time は ±2s 程度で妥当
    assert abs(r.peak_time - tac.ground_truth["true_peak_time"]) < 2.0


def test_peak_detection_plausible_location():
    """raw ピーク検出が真の peak_time 近傍を返す。"""
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
    """全ゼロ曲線でも例外を投げず success=False を返す (silent failure 禁止)。"""
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
