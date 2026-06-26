# -*- coding: utf-8 -*-
"""
a-LUT 検証図ジェネレータ (IORN-001 用)
======================================

ASIST-Japan 標準 a-LUT 実装の検証図を生成する (要件 7):

  * grayscale マップ
  * ASIST-LUT マップ
  * ヒストグラム (量的値分布 + 表示窓 vmin/vmax)
  * カラーバー (ASIST 慣例)
  * grayscale ↔ ASIST 並置比較図

入力データの優先順位:
  1. ``output/maps/<map_type>.npy`` が存在すればそれを使用 (実データ)。
  2. 無ければ決定論的な合成ファントム (再現可能) を生成。

出力先: ``output/figures/a_lut/``

実行:
    python make_a_lut_figures.py                # 全マップ種別
    python make_a_lut_figures.py cbf cbv        # 指定種別のみ
"""

from __future__ import annotations

import os
import sys
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ctp_core.a_lut import (
    apply_a_lut,
    export_colorbar,
    resolve_range,
    to_mpl_colormap,
    MAP_PRESETS,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_REAL_MAP_DIR = os.path.join(_HERE, "output", "maps")
_FIG_DIR = os.path.join(_HERE, "output", "figures", "a_lut")


def _phantom(map_type: str, shape=(128, 128)) -> np.ndarray:
    """決定論的な合成灌流ファントムを生成する (再現可能・乱数不使用)。

    放射状の値勾配 + 中央に低灌流コア (虚血コア) + 背景マスク (円外=NaN)。
    """
    preset = MAP_PRESETS[map_type]
    vmin, vmax = preset["vmin"], preset["vmax"]
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    r_norm = r / r.max()

    # 外周ほど高値の滑らかな勾配 (CBF/CBV 系)。時間系 (MTT/TTP/Tmax) は逆勾配。
    base = vmin + (vmax - vmin) * r_norm
    if map_type in ("mtt", "ttp", "tmax"):
        base = vmax - (vmax - vmin) * r_norm

    # 中央の低灌流コア (CBF/CBV は低下、時間系は延長)
    core = r < (0.22 * r.max())
    if map_type in ("mtt", "ttp", "tmax"):
        base[core] = vmax * 0.95
    else:
        base[core] = vmin + (vmax - vmin) * 0.08

    # 円外を NaN (頭蓋外/マスク外) に
    base[r > 0.92 * r.max()] = np.nan
    return base


def _load_map(map_type: str) -> tuple[np.ndarray, str]:
    """実マップ (.npy) があれば読み込み、無ければ合成ファントムを返す。"""
    real = os.path.join(_REAL_MAP_DIR, f"{map_type}.npy")
    if os.path.exists(real):
        return np.load(real), "real"
    return _phantom(map_type), "phantom"


def _make_for_map(map_type: str, out_dir: str) -> None:
    preset = MAP_PRESETS[map_type]
    data, src = _load_map(map_type)
    vmin, vmax = resolve_range(data, map_type, None, None)
    label = preset["label"]
    unit = preset["unit"]
    valid = np.isfinite(data)

    # --- 1. grayscale マップ ---
    rgb_gray = apply_a_lut(data, map_type=map_type, lut="grayscale")
    _imsave_rgb(rgb_gray, os.path.join(out_dir, f"{map_type}_grayscale.png"),
                title=f"{label} — grayscale")

    # --- 2. ASIST-LUT マップ ---
    rgb_asist = apply_a_lut(data, map_type=map_type, lut="asist")
    _imsave_rgb(rgb_asist, os.path.join(out_dir, f"{map_type}_asist.png"),
                title=f"{label} — ASIST a-LUT")

    # --- 3. ヒストグラム (量的値分布 + 表示窓) ---
    _hist(data[valid], vmin, vmax, label, unit,
          os.path.join(out_dir, f"{map_type}_histogram.png"))

    # --- 4. カラーバー (ASIST 慣例) ---
    export_colorbar(os.path.join(out_dir, f"{map_type}_colorbar.png"),
                    map_type=map_type, lut="asist", orientation="horizontal")

    # --- 5. 並置比較 (grayscale | ASIST | colorbar) ---
    _comparison(data, map_type, vmin, vmax, label, unit, src,
                os.path.join(out_dir, f"{map_type}_comparison.png"))

    print(f"  [{map_type}] source={src}  vmin={vmin:g} vmax={vmax:g}  -> {out_dir}")


def _imsave_rgb(rgb: np.ndarray, path: str, title: str) -> None:
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.imshow(rgb)
    ax.set_title(title, fontsize=9)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _hist(values, vmin, vmax, label, unit, path) -> None:
    fig, ax = plt.subplots(figsize=(5, 3.2))
    ax.hist(values, bins=64, color="0.4")
    ax.axvline(vmin, color="tab:blue", ls="--", lw=1, label=f"vmin={vmin:g}")
    ax.axvline(vmax, color="tab:red", ls="--", lw=1, label=f"vmax={vmax:g}")
    ax.set_xlabel(f"{label}  [{unit}]" if unit else label)
    ax.set_ylabel("voxel count")
    ax.set_title("Quantitative value distribution", fontsize=9)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _comparison(data, map_type, vmin, vmax, label, unit, src, path) -> None:
    cmap = to_mpl_colormap("asist")
    cmap.set_bad((0, 0, 0))  # NaN は黒背景
    masked = np.ma.masked_invalid(data)

    fig, axes = plt.subplots(1, 2, figsize=(8, 4.2))
    # grayscale
    axes[0].imshow(np.ma.masked_invalid(data), cmap="gray",
                   vmin=vmin, vmax=vmax)
    axes[0].set_title("grayscale", fontsize=9)
    axes[0].axis("off")
    # ASIST
    im = axes[1].imshow(masked, cmap=cmap, vmin=vmin, vmax=vmax)
    axes[1].set_title("ASIST a-LUT", fontsize=9)
    axes[1].axis("off")
    cbar = fig.colorbar(im, ax=axes[1], fraction=0.046, pad=0.04)
    cbar.set_label(f"{label}  [{unit}]" if unit else label, fontsize=8)

    fig.suptitle(f"{label}  (source: {src})", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main(argv) -> int:
    types = [t.lower() for t in argv[1:]] or list(MAP_PRESETS.keys())
    unknown = [t for t in types if t not in MAP_PRESETS]
    if unknown:
        print(f"未知のマップ種別: {unknown} (有効値: {list(MAP_PRESETS)})")
        return 2

    os.makedirs(_FIG_DIR, exist_ok=True)
    print(f"検証図を生成中 -> {_FIG_DIR}")
    for t in types:
        _make_for_map(t, _FIG_DIR)
    print("完了。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
