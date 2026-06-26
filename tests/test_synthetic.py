# -*- coding: utf-8 -*-
"""合成 TAC ジェネレータ (ctp_core.synthetic) の検証。"""

import _pathfix  # noqa: F401
import numpy as np

from ctp_core.synthetic import generate_synthetic_tac, SyntheticTAC


def test_returns_synthetic_tac():
    tac = generate_synthetic_tac(seed=0)
    assert isinstance(tac, SyntheticTAC)
    assert tac.time.shape == tac.clean.shape == tac.noisy.shape


def test_time_sampling():
    tac = generate_synthetic_tac(n_time_points=50, dt=0.5, seed=0)
    assert tac.time.shape == (50,)
    assert np.isclose(tac.time[1] - tac.time[0], 0.5)


def test_deterministic_with_seed():
    """固定シードで noisy 曲線まで完全再現 (要件: fixed random seed)。"""
    a = generate_synthetic_tac(seed=42)
    b = generate_synthetic_tac(seed=42)
    assert np.array_equal(a.noisy, b.noisy)
    assert np.array_equal(a.clean, b.clean)


def test_different_seed_changes_noise():
    a = generate_synthetic_tac(seed=1)
    b = generate_synthetic_tac(seed=2)
    assert not np.array_equal(a.noisy, b.noisy)
    # clean (真の曲線) はシードに依らず同一
    assert np.array_equal(a.clean, b.clean)


def test_curve_generation_gamma_shape():
    """生成曲線は gamma-variate 形状: t0 以前はゼロ、単峰。"""
    tac = generate_synthetic_tac(amplitude=60, t0=8, alpha=3, beta=2,
                                 snr=None, noise_std=0.0, seed=0)
    # t<=t0 はゼロ
    pre = tac.clean[tac.time <= 8.0]
    assert np.allclose(pre, 0.0)
    # ピーク高は amplitude 近傍
    assert abs(tac.clean.max() - 60.0) < 1e-6


def test_ground_truth_peak_time_analytic():
    """真の peak_time = t0 + alpha*beta。"""
    tac = generate_synthetic_tac(amplitude=50, t0=6, alpha=4, beta=1.5, seed=0)
    assert np.isclose(tac.ground_truth["true_peak_time"], 6 + 4 * 1.5)


def test_snr_controls_noise_std():
    tac = generate_synthetic_tac(amplitude=100, snr=10, seed=0)
    assert np.isclose(tac.ground_truth["noise_std"], 10.0)


def test_noise_std_overrides_snr():
    tac = generate_synthetic_tac(amplitude=100, snr=10, noise_std=3.0, seed=0)
    assert np.isclose(tac.ground_truth["noise_std"], 3.0)


def test_zero_noise_clean_equals_noisy():
    tac = generate_synthetic_tac(noise_std=0.0, seed=0)
    assert np.array_equal(tac.clean, tac.noisy)


def test_recirculation_adds_late_signal():
    """再循環成分は後半に追加信号をもたらす。"""
    base = generate_synthetic_tac(recirculation=False, noise_std=0.0, seed=0)
    rec = generate_synthetic_tac(recirculation=True, noise_std=0.0, seed=0)
    # 後半 (t > true_peak_time) の総和が増える
    late = base.time > base.ground_truth["true_peak_time"]
    assert rec.clean[late].sum() > base.clean[late].sum()


def test_outputs_finite():
    tac = generate_synthetic_tac(seed=0)
    assert np.all(np.isfinite(tac.clean))
    assert np.all(np.isfinite(tac.noisy))


def test_invalid_params_raise():
    for bad in (dict(n_time_points=2), dict(dt=0.0), dict(dt=-1.0)):
        try:
            generate_synthetic_tac(seed=0, **bad)
        except ValueError:
            continue
        raise AssertionError(f"invalid params should raise: {bad}")


if __name__ == "__main__":
    import _runner
    _runner.run(globals())
