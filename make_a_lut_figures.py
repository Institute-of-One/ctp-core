# -*- coding: utf-8 -*-
"""
a-LUT validation figure generator (for IORN-001)
======================================

Generates the validation figures for the ASIST-Japan standard a-LUT implementation:

  * the grayscale map
  * the ASIST-LUT map
  * a histogram: the distribution of values with the display window vmin/vmax
  * a colour bar, in the ASIST style
  * a side-by-side comparison of grayscale and ASIST

Order of preference for the input data:
  1. use ``output/maps/<map_type>.npy`` when it exists, that is, real data;
  2. otherwise generate a deterministic, reproducible synthetic phantom.

Output directory: ``output/figures/a_lut/``

Run:
    python make_a_lut_figures.py                # every map type
    python make_a_lut_figures.py cbf cbv        # only the named types
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
    """Generate a deterministic synthetic perfusion phantom, using no randomness.

    A radial gradient in value, a low-perfusion core at the centre standing for an
    ischaemic core, and a background mask that sets everything outside a circle to NaN.
    """
    preset = MAP_PRESETS[map_type]
    vmin, vmax = preset["vmin"], preset["vmax"]
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    r_norm = r / r.max()

    # A smooth gradient rising outwards, for CBF and CBV; the time-based maps
    # (MTT, TTP, Tmax) use the opposite gradient.
    base = vmin + (vmax - vmin) * r_norm
    if map_type in ("mtt", "ttp", "tmax"):
        base = vmax - (vmax - vmin) * r_norm

    # The low-perfusion core at the centre: CBF and CBV fall, the times lengthen.
    core = r < (0.22 * r.max())
    if map_type in ("mtt", "ttp", "tmax"):
        base[core] = vmax * 0.95
    else:
        base[core] = vmin + (vmax - vmin) * 0.08

    # Outside the circle becomes NaN, standing for outside the skull or the mask.
    base[r > 0.92 * r.max()] = np.nan
    return base


def _load_map(map_type: str) -> tuple[np.ndarray, str]:
    """Load the real map (.npy) when there is one, otherwise return the phantom."""
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

    # --- 1. the grayscale map ---
    rgb_gray = apply_a_lut(data, map_type=map_type, lut="grayscale")
    _imsave_rgb(rgb_gray, os.path.join(out_dir, f"{map_type}_grayscale.png"),
                title=f"{label} — grayscale")

    # --- 2. the ASIST-LUT map ---
    rgb_asist = apply_a_lut(data, map_type=map_type, lut="asist")
    _imsave_rgb(rgb_asist, os.path.join(out_dir, f"{map_type}_asist.png"),
                title=f"{label} — ASIST a-LUT")

    # --- 3. the histogram: value distribution with the display window ---
    _hist(data[valid], vmin, vmax, label, unit,
          os.path.join(out_dir, f"{map_type}_histogram.png"))

    # --- 4. the colour bar, in the ASIST style ---
    export_colorbar(os.path.join(out_dir, f"{map_type}_colorbar.png"),
                    map_type=map_type, lut="asist", orientation="horizontal")

    # --- 5. side by side: grayscale | ASIST | colour bar ---
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
    cmap.set_bad((0, 0, 0))  # NaN gets a black background
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
        print(f"Unknown map type: {unknown} (valid values: {list(MAP_PRESETS)})")
        return 2

    os.makedirs(_FIG_DIR, exist_ok=True)
    print(f"Generating the validation figures -> {_FIG_DIR}")
    for t in types:
        _make_for_map(t, _FIG_DIR)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
