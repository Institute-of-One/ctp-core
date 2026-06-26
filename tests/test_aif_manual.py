# -*- coding: utf-8 -*-
"""手動AIF抽出 (AIFDetector.extract_aif_at) の検証 (合成データのみ)。"""

import _pathfix  # noqa: F401
import numpy as np

from ctp_core.aif_detection import AIFDetector
from ctp_core.gamma_fit import fit_gamma_variate


def _synthetic_volume():
    nt, ns, R, C = 20, 2, 32, 32
    vol = np.full((nt, ns, R, C), 40.0)
    t = np.arange(nt)
    bolus = 200.0 * np.exp(-((t - 6) ** 2) / 4.0)
    vol[:, 0, 16, 16] += bolus
    vol[:, 0, 16, 17] += bolus * 0.9
    meta = {"n_times": nt, "rows": R, "cols": C,
            "time_seconds": list(np.arange(nt, dtype=float))}
    return vol, meta


def test_extract_aif_at_returns_curve():
    vol, meta = _synthetic_volume()
    det = AIFDetector(vol, meta)
    res = det.extract_aif_at(16, 16, slice_index=0, radius=2)
    assert res.aif_curve is not None
    assert res.aif_curve.shape == (meta["n_times"],)
    assert res.n_aif_voxels > 0
    assert res.aif_center == (16.0, 16.0)
    assert res.detection_info["manual"] is True


def test_extract_aif_at_detects_bolus_peak():
    vol, meta = _synthetic_volume()
    det = AIFDetector(vol, meta)
    res = det.extract_aif_at(16, 16, slice_index=0, radius=2)
    # ボーラスのピークは t=6 付近
    assert abs(int(np.argmax(res.aif_enhancement)) - 6) <= 1
    assert np.max(res.aif_enhancement) > 0


def test_extract_aif_at_does_not_mutate_volume():
    vol, meta = _synthetic_volume()
    snapshot = vol.copy()
    AIFDetector(vol, meta).extract_aif_at(16, 16, slice_index=0, radius=3)
    assert np.array_equal(vol, snapshot)


def test_extract_aif_at_clips_out_of_bounds():
    vol, meta = _synthetic_volume()
    det = AIFDetector(vol, meta)
    # 範囲外座標でも例外を投げずクリップされる
    res = det.extract_aif_at(-5, 999, slice_index=0, radius=2)
    assert res.n_aif_voxels >= 1
    assert 0 <= res.aif_center[0] < meta["rows"]
    assert 0 <= res.aif_center[1] < meta["cols"]


def test_manual_aif_curve_is_gamma_fittable():
    vol, meta = _synthetic_volume()
    det = AIFDetector(vol, meta)
    res = det.extract_aif_at(16, 16, slice_index=0, radius=2)
    fit = fit_gamma_variate(np.asarray(res.time_seconds), res.aif_enhancement)
    assert fit.success
    assert fit.r_squared > 0.9
    assert np.isfinite(fit.peak_time)


if __name__ == "__main__":
    import _runner
    _runner.run(globals())
