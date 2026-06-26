# -*- coding: utf-8 -*-
"""ASIST a-LUT のコア検証 (ctp_core.a_lut)。

同梱 LUT 資産 (ctp_core/assets/alut.csv) が importlib.resources で安全に
解決されることを前提に、固定スカラー入力に対する **決定論的 RGB 出力** と
量的値の不変性を確認する。
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
    assert tuple(lut[0]) == (0, 0, 0)       # 低値 = 黒
    assert tuple(lut[255]) == (255, 0, 0)   # 高値 = 赤


def test_deterministic_rgb_for_fixed_scalar():
    """固定スカラー値 → bit-exact に同一 RGB (要件: deterministic RGB output)。"""
    d = np.array([[0.0, 40.0, 80.0]])
    r1 = apply_a_lut(d, map_type="cbf")
    r2 = apply_a_lut(d, map_type="cbf")
    assert np.array_equal(r1, r2)


def test_fixed_scalar_exact_rgb_values():
    """vmin=0,vmax=80 のとき 0/40/80 -> LUT index 0/128/255 の RGB。"""
    lut = load_a_lut("asist")
    d = np.array([[0.0, 40.0, 80.0]])
    rgb = apply_a_lut(d, map_type="cbf")
    assert tuple(rgb[0, 0]) == tuple(lut[0])
    assert tuple(rgb[0, 1]) == tuple(lut[128])
    assert tuple(rgb[0, 2]) == tuple(lut[255])


def test_quantitative_values_unchanged():
    """LUT 適用は可視化のみ: 入力スカラー配列を破壊しない。"""
    d = np.array([[10.0, 20.0], [30.0, 40.0]])
    snapshot = d.copy()
    _ = apply_a_lut(d, map_type="cbf")
    assert np.array_equal(d, snapshot)


def test_scalar_to_index_midpoint():
    assert scalar_to_index(np.array([40.0]), 0.0, 80.0)[0] == 128


if __name__ == "__main__":
    import _runner
    _runner.run(globals())
