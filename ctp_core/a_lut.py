# -*- coding: utf-8 -*-
"""
ASIST-Japan standard perfusion colour mapping (a-LUT)
=========================================================

ASIST-Japan (Acute Stroke Imaging Standardization Group Japan,
Renders CT- and MR-perfusion maps in a standardized colour scheme, using the
standard lookup table (a-LUT) published by ASIST-Japan.

Background:
-----
The colour scale of a perfusion image differs between scanners and between
institutions, so the same data can look very different. The ASIST-Japan CT/MR
Perfusion Imaging Practical Guideline 2006 states that standardizing the display
is desirable, and publishes a standard LUT as a 256-level RGB table.

    Source: ASIST-Japan  https://asist.umin.jp/  (data/alut.csv)
            CT/MR Perfusion Imaging Practical Guideline 2006
          https://asist.umin.jp/data/guidelineCtpMrp2006.pdf

The a-LUT colour order, low to high:
    black -> purple -> blue -> cyan -> green -> yellow -> orange -> red
    (index 0 = black (0,0,0), index 255 = red (255,0,0))
By convention high values are red and low values blue or black.

Design:
--------
- Quantitative voxel values are never altered. The LUT affects **display only**.
  apply_a_lut() always returns a new RGB array and never modifies its input.
- For a fixed scalar value the RGB output is deterministic.
- Grayscale, the ASIST standard, and any research LUT can be selected.

Main API:
--------
    load_a_lut(name='asist')        -> obtain the LUT as (256, 3) uint8
    apply_a_lut(data, ...)          -> scalar map to (H, W, 3) uint8 RGB
    export_png_with_a_lut(data, ..) -> write an RGB PNG
    export_colorbar(...)            -> write a colour bar PNG in the ASIST style

Usage:
    from a_lut import apply_a_lut, export_png_with_a_lut, MAP_PRESETS
    rgb = apply_a_lut(cbf_map, map_type='cbf')          # the ASIST standard
    export_png_with_a_lut(cbf_map, 'cbf.png', map_type='cbf')
"""

from __future__ import annotations

import os
import csv
import numpy as np

# ---------------------------------------------------------------------------
# Constants and settings
# ---------------------------------------------------------------------------

#: Number of levels in the a-LUT; the ASIST standard is 256.
LUT_SIZE = 256

def _resolve_default_alut_csv() -> str:
    """Resolve the absolute path of the packaged standard a-LUT CSV.

    So that the file is still readable once the project is packaged (pip install or a
    wheel), this looks first for the resource shipped inside the package
    (ctp_core/assets/alut.csv) through importlib.resources, and falls back to a path
    relative to this file. Neither touches quantitative values; this only locates the
    colour table.
    """
    # 1) The resource shipped inside the package, robust once installed.
    try:
        from importlib.resources import files
        res = files("ctp_core").joinpath("assets", "alut.csv")
        if res.is_file():
            return str(res)
    except Exception:
        pass
    # 2) Fallback: assets/alut.csv beside this module, as laid out in the source tree.
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "alut.csv"
    )


#: Default location of the a-LUT CSV, shipped as ctp_core/assets/alut.csv.
_DEFAULT_ALUT_CSV = _resolve_default_alut_csv()

#: RGB background assigned to voxels outside the mask or invalid (NaN, mask=False).
BACKGROUND_RGB = (0, 0, 0)

#: The available LUT modes.
LUT_MODES = ("grayscale", "asist", "custom")


#: Standard display settings for each perfusion parameter.
#: vmin and vmax follow the ASIST guideline and the display ranges customary in
#: acute stroke. These are a display window and do not affect the values themselves.
MAP_PRESETS = {
    "cbf": {
        "label": "CBF (Cerebral Blood Flow)",
        "unit": "mL/100g/min",
        "vmin": 0.0,
        "vmax": 80.0,
    },
    "cbv": {
        "label": "CBV (Cerebral Blood Volume)",
        "unit": "mL/100g",
        "vmin": 0.0,
        "vmax": 8.0,
    },
    "mtt": {
        "label": "MTT (Mean Transit Time)",
        "unit": "s",
        "vmin": 0.0,
        "vmax": 12.0,
    },
    "ttp": {
        "label": "TTP (Time To Peak)",
        "unit": "s",
        "vmin": 0.0,
        "vmax": 25.0,
    },
    # Tmax is for future use; the current pipeline already computes it.
    "tmax": {
        "label": "Tmax (Time to Max of residue)",
        "unit": "s",
        "vmin": 0.0,
        "vmax": 14.0,
    },
}


# ---------------------------------------------------------------------------
# Loading the LUT
# ---------------------------------------------------------------------------

# In-process cache, to avoid re-reading the same LUT.
_LUT_CACHE: dict = {}


def _load_alut_csv(path: str) -> np.ndarray:
    """Read an ASIST a-LUT CSV (Index,R,G,B; 256 rows) as (256, 3) uint8."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"ASIST a-LUT CSV not found: {path}\n"
            f"Download it from https://asist.umin.jp/data/alut.csv and place it in assets/."
        )

    rows = []
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        # If the first row is numeric the CSV has no header, so treat it as data.
        if header is not None and _looks_numeric(header):
            rows.append([int(float(x)) for x in header[1:4]])
        for row in reader:
            if len(row) < 4 or not row[0].strip():
                continue
            rows.append([int(float(row[1])), int(float(row[2])), int(float(row[3]))])

    lut = np.asarray(rows, dtype=np.uint8)
    if lut.shape != (LUT_SIZE, 3):
        raise ValueError(
            f"The a-LUT has the wrong shape: {lut.shape} (expected ({LUT_SIZE}, 3))"
        )
    return lut


def _looks_numeric(row) -> bool:
    try:
        [float(x) for x in row[:4]]
        return True
    except (ValueError, IndexError):
        return False


def _grayscale_lut() -> np.ndarray:
    """A linear grayscale LUT from 0 to 255, shape (256, 3)."""
    ramp = np.arange(LUT_SIZE, dtype=np.uint8)
    return np.stack([ramp, ramp, ramp], axis=1)


def load_a_lut(name: str = "asist", path: str | None = None) -> np.ndarray:
    """Obtain a LUT as a (256, 3) uint8 array.

    Args:
        name: 'asist'  -> the ASIST-Japan standard a-LUT (assets/alut.csv)
              'grayscale' -> a linear grayscale
              'custom'  -> read the CSV given by ``path``
        path: overrides the CSV path when name is 'asist' or 'custom'.
              For 'asist' with None, the default assets/alut.csv is used.

    Returns:
        The RGB LUT as (256, 3) uint8.

    Note:
        Quantitative values are untouched; this only returns a colour table.
    """
    name = name.lower()
    cache_key = (name, path)
    if cache_key in _LUT_CACHE:
        return _LUT_CACHE[cache_key].copy()

    if name == "grayscale":
        lut = _grayscale_lut()
    elif name == "asist":
        lut = _load_alut_csv(path or _DEFAULT_ALUT_CSV)
    elif name == "custom":
        if not path:
            raise ValueError("name='custom' requires a path to a CSV.")
        lut = _load_alut_csv(path)
    else:
        raise ValueError(
            f"Unknown LUT name: {name!r} (valid values: {LUT_MODES})"
        )

    _LUT_CACHE[cache_key] = lut
    return lut.copy()


# ---------------------------------------------------------------------------
# Applying the LUT (scalar -> RGB)
# ---------------------------------------------------------------------------

def scalar_to_index(
    data: np.ndarray, vmin: float, vmax: float
) -> np.ndarray:
    """Normalize a scalar over [vmin, vmax] into a LUT index in 0..255.

    Deterministic: the same (value, vmin, vmax) always gives the same index.
    A degenerate vmax <= vmin returns all zeros rather than dividing by zero.
    """
    data = np.asarray(data, dtype=np.float64)
    span = float(vmax) - float(vmin)
    if span <= 0:
        norm = np.zeros_like(data)
    else:
        norm = (data - float(vmin)) / span
    norm = np.clip(norm, 0.0, 1.0)
    idx = np.round(norm * (LUT_SIZE - 1)).astype(np.int64)
    return np.clip(idx, 0, LUT_SIZE - 1)


def apply_a_lut(
    data: np.ndarray,
    map_type: str | None = None,
    lut: str | np.ndarray = "asist",
    vmin: float | None = None,
    vmax: float | None = None,
    mask: np.ndarray | None = None,
    custom_lut_path: str | None = None,
) -> np.ndarray:
    """Apply the LUT to a scalar map and return an RGB image, (H, W, 3) uint8.

    **Quantitative voxel values are not changed.** The input ``data`` is treated as
    read-only and a new RGB array is created.

    Args:
        data: a two-dimensional scalar map, for example a CBF map.
        map_type: 'cbf'/'cbv'/'mtt'/'ttp'/'tmax'. When vmin and vmax are not given,
                  the standard range from MAP_PRESETS is used.
        lut: the name of a LUT mode ('asist'/'grayscale'/'custom'), or a
             (256, 3) LUT array given directly.
        vmin, vmax: the lower and upper bound of the display window. None takes the
                    preset for map_type, or failing that the min and max of the
                    finite values in data.
        mask: colour only the voxels that are True. False and NaN get BACKGROUND_RGB.
        custom_lut_path: the CSV path used when lut='custom'.

    Returns:
        The RGB image, (H, W, 3) uint8.
    """
    data = np.asarray(data, dtype=np.float64)
    if data.ndim != 2:
        raise ValueError(f"data must be two-dimensional: shape={data.shape}")

    # Resolve the LUT
    if isinstance(lut, np.ndarray):
        table = lut
        if table.shape != (LUT_SIZE, 3):
            raise ValueError(f"Invalid LUT array shape: {table.shape}")
        table = table.astype(np.uint8)
    else:
        table = load_a_lut(lut, path=custom_lut_path)

    # Resolve the display range
    vmin, vmax = resolve_range(data, map_type, vmin, vmax, mask)

    # Valid-voxel mask: exclude NaN and Inf, and AND with mask when it is given.
    valid = np.isfinite(data)
    if mask is not None:
        valid = valid & np.asarray(mask, dtype=bool)

    # Normalize and index; NaN is filled with 0 before indexing.
    safe = np.where(valid, data, vmin)
    idx = scalar_to_index(safe, vmin, vmax)

    rgb = table[idx]  # (H, W, 3)

    # Give the invalid voxels the background colour
    rgb = rgb.copy()
    rgb[~valid] = np.array(BACKGROUND_RGB, dtype=np.uint8)
    return rgb


def resolve_range(data, map_type, vmin, vmax, mask=None):
    """Settle vmin and vmax. Priority: explicit values, then the preset, then the data."""
    preset = MAP_PRESETS.get(map_type.lower()) if map_type else None
    if vmin is None:
        vmin = preset["vmin"] if preset else None
    if vmax is None:
        vmax = preset["vmax"] if preset else None

    if vmin is None or vmax is None:
        finite = np.asarray(data, dtype=np.float64)
        valid = np.isfinite(finite)
        if mask is not None:
            valid = valid & np.asarray(mask, dtype=bool)
        vals = finite[valid]
        if vals.size == 0:
            data_min, data_max = 0.0, 1.0
        else:
            data_min, data_max = float(np.min(vals)), float(np.max(vals))
        if vmin is None:
            vmin = data_min
        if vmax is None:
            vmax = data_max if data_max > vmin else vmin + 1.0
    return float(vmin), float(vmax)


# ---------------------------------------------------------------------------
# Conversion to a matplotlib Colormap, for use with existing display code
# ---------------------------------------------------------------------------

def to_mpl_colormap(lut: str | np.ndarray = "asist", name: str = "asist"):
    """Convert a LUT into a matplotlib ListedColormap.

    This lets existing imshow(cmap=...) code adopt the LUT with a minimal change.
    """
    from matplotlib.colors import ListedColormap

    table = lut if isinstance(lut, np.ndarray) else load_a_lut(lut)
    return ListedColormap(table.astype(np.float64) / 255.0, name=name)


# ---------------------------------------------------------------------------
# Writing PNGs
# ---------------------------------------------------------------------------

def _save_rgb_png(rgb: np.ndarray, path: str) -> None:
    """Save (H, W, 3) uint8 RGB as a PNG, preferring PIL and falling back to matplotlib."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    try:
        from PIL import Image
        Image.fromarray(rgb.astype(np.uint8), mode="RGB").save(path)
    except ImportError:
        import matplotlib.image as mpimg
        mpimg.imsave(path, rgb.astype(np.uint8))


def export_png_with_a_lut(
    data: np.ndarray,
    path: str,
    map_type: str | None = None,
    lut: str | np.ndarray = "asist",
    vmin: float | None = None,
    vmax: float | None = None,
    mask: np.ndarray | None = None,
    custom_lut_path: str | None = None,
) -> np.ndarray:
    """Apply the LUT to a scalar map and write a bare RGB PNG, with no axes or margins.

    Quantitative values are not saved; this is for display only. Keep them
    separately, for example as .npy.

    Returns:
        The (H, W, 3) uint8 RGB array that was written.
    """
    rgb = apply_a_lut(
        data, map_type=map_type, lut=lut, vmin=vmin, vmax=vmax,
        mask=mask, custom_lut_path=custom_lut_path,
    )
    _save_rgb_png(rgb, path)
    return rgb


# ---------------------------------------------------------------------------
# Colour bar (the ASIST style: a horizontal gradient with ticks)
# ---------------------------------------------------------------------------

def make_colorbar_strip(
    lut: str | np.ndarray = "asist",
    orientation: str = "horizontal",
    length: int = 256,
    thickness: int = 32,
) -> np.ndarray:
    """Build a continuous colour-bar image from the LUT, (H, W, 3) uint8.

    Following the alut-horizontal.gif published by ASIST, the default is horizontal,
    """
    table = lut if isinstance(lut, np.ndarray) else load_a_lut(lut)
    idx = scalar_to_index(np.linspace(0, 1, length), 0.0, 1.0)
    line = table[idx]  # (length, 3)

    if orientation == "horizontal":
        strip = np.broadcast_to(line[np.newaxis, :, :], (thickness, length, 3))
    elif orientation == "vertical":
        # Vertical runs low at the bottom to high at the top.
        line = line[::-1]
        strip = np.broadcast_to(line[:, np.newaxis, :], (length, thickness, 3))
    else:
        raise ValueError("orientation must be 'horizontal' or 'vertical'")
    return np.ascontiguousarray(strip, dtype=np.uint8)


def export_colorbar(
    path: str,
    map_type: str | None = None,
    lut: str | np.ndarray = "asist",
    vmin: float | None = None,
    vmax: float | None = None,
    orientation: str = "horizontal",
    label: str | None = None,
    unit: str | None = None,
) -> None:
    """Save a colour-bar figure with ticks and labels as a PNG, in the ASIST style."""
    import matplotlib
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    preset = MAP_PRESETS.get(map_type.lower()) if map_type else None
    if vmin is None:
        vmin = preset["vmin"] if preset else 0.0
    if vmax is None:
        vmax = preset["vmax"] if preset else 1.0
    if label is None:
        label = preset["label"] if preset else (map_type or "")
    if unit is None:
        unit = preset["unit"] if preset else ""

    strip = make_colorbar_strip(lut, orientation=orientation)

    if orientation == "horizontal":
        fig, ax = plt.subplots(figsize=(6, 1.4))
        ax.imshow(strip, extent=[vmin, vmax, 0, 1], aspect="auto")
        ax.set_yticks([])
        ax.set_xlabel(f"{label}  [{unit}]" if unit else label)
    else:
        fig, ax = plt.subplots(figsize=(1.8, 6))
        ax.imshow(strip, extent=[0, 1, vmin, vmax], aspect="auto")
        ax.set_xticks([])
        ax.set_ylabel(f"{label}  [{unit}]" if unit else label)

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
