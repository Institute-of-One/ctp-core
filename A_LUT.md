# The ASIST-Japan standard perfusion colour mapping (a-LUT)

Implementation notes for the standardized visualization of perfusion maps in ctp-core /
IORN-001. The text here is written so that it can be carried over into the **Methods**
section of IORN-001.

---

## 1. Background and purpose

The colour scale, or lookup table (LUT), used for perfusion images (CT and MR) differs
between scanners and between institutions, so the same quantitative data can be displayed
in very different colours. That harms comparability between readers and between
institutions, and stands in the way of reproducible research and reporting.

**ASIST-Japan** (the Acute Stroke Imaging Standardization Group Japan) recommends
standardizing the display in its *CT/MR Perfusion Imaging Practical Guideline 2006*, and
publishes a standard lookup table, the **a-LUT**, as a 256-level RGB table.

IORN-001 aims at a transparent and reproducible CT-perfusion pipeline, and a standardized
display is part of that reproducibility. This implementation follows the ASIST-Japan
recommendation explicitly.

### Sources and references

- ASIST-Japan: <https://asist.umin.jp/>
- The standard LUT (CSV): <https://asist.umin.jp/data/alut.csv>
- CT/MR Perfusion Imaging Practical Guideline 2006:
  <https://asist.umin.jp/data/guidelineCtpMrp2006.pdf>

Packaged assets (`ctp_core/assets/`):

| File | Contents |
|---|---|
| `alut.csv` | the a-LUT itself (`Index,R,G,B`; 256 rows) -- the canonical source this implementation reads |
| `alut.tif` | a TIFF rendering of the a-LUT, for reference |
| `ASIST.lut` | the LUT as a binary, for ImageJ and similar tools, for reference |
| `alut-horizontal.gif` | the horizontal colour bar published by ASIST, to confirm the convention |

---

## 2. The a-LUT colour order

The a-LUT is a 256-level RGB table running from low to high values as:

```
black -> purple -> blue -> cyan -> green -> yellow -> orange -> red
index 0 = (0,0,0) black      index 255 = (255,0,0) red
```

By convention **high values are red and low values blue or black**. In acute stroke this
makes the regions of reduced CBF and CBV -- the ischaemic core -- and the regions of
prolonged MTT, TTP and Tmax immediately recognisable.

---

## 3. Design decisions (important)

1. **Quantitative voxel values are never altered.** The LUT affects *display only*.
   `apply_a_lut()` always returns a new RGB array and never modifies its input, which is
   guaranteed by the unit test `test_quantitative_values_unchanged`. Keep the
   quantitative values separately, as `.npy` or similar; do not save them in the PNG.
2. **Deterministic.** For a fixed scalar value and a fixed display window the RGB output
   is bit-exact reproducible (`test_deterministic_rgb_for_fixed_scalar`,
   `test_fixed_scalar_exact_rgb_values`). No randomness is used anywhere.
3. **The LUT is selectable**: `grayscale`, `asist` (the standard) or `custom` (any CSV,
   for research use).
4. **Voxels outside the mask or invalid** (NaN, Inf, mask=False) are given the background
   colour, black by default.

---

## 4. The display window (vmin/vmax)

The standard display range of each perfusion parameter. This is a **display window** and
does not affect the values themselves. The ranges follow those customary in acute stroke
and the ASIST guideline.

| map_type | Label | Unit | vmin | vmax |
|---|---|---|---|---|
| `cbf` | Cerebral Blood Flow | mL/100g/min | 0 | 80 |
| `cbv` | Cerebral Blood Volume | mL/100g | 0 | 8 |
| `mtt` | Mean Transit Time | s | 0 | 12 |
| `ttp` | Time To Peak | s | 0 | 25 |
| `tmax`| Time to Max of residue | s | 0 | 14 |

The display window is resolved in this order: **explicit vmin/vmax, then the preset for
map_type, then the minimum and maximum measured in the data.**

---

## 5. The algorithm

Converting a scalar map `data` into an RGB image:

1. Resolve the display window `(vmin, vmax)`; see section 4.
2. Normalize: `norm = clip((data - vmin) / (vmax - vmin), 0, 1)`.
   A degenerate `vmax <= vmin` gives all zeros rather than dividing by zero.
3. Index: `idx = round(norm * 255)`, in [0, 255], to the nearest level.
4. Look up directly: `rgb = LUT[idx]`.
5. Overwrite the invalid voxels (NaN, Inf, mask=False) with the background colour.

> A worked midpoint: `data=40, vmin=0, vmax=80` gives `norm=0.5` and
> `idx=round(127.5)=128`. At the ends, `data=0` gives index 0 and `data=80` gives 255.

---

## 6. API

Module: [`ctp_core/a_lut.py`](ctp_core/a_lut.py)

```python
from ctp_core.a_lut import (
    load_a_lut,            # obtain the (256,3) uint8 LUT
    apply_a_lut,           # scalar map -> (H,W,3) uint8 RGB
    export_png_with_a_lut, # write a bare RGB PNG, no axes or margins
    export_colorbar,       # write a colour bar PNG with ticks and labels
    make_colorbar_strip,   # build the colour bar image (H,W,3)
    to_mpl_colormap,       # convert to a matplotlib ListedColormap, for existing imshow code
    MAP_PRESETS,           # the display-window presets
)

# Example: render a CBF map as a PNG in the ASIST standard colours.
# The quantitative values are unchanged.
rgb = apply_a_lut(cbf_map, map_type="cbf")                 # the ASIST standard
export_png_with_a_lut(cbf_map, "cbf.png", map_type="cbf")
export_colorbar("cbf_bar.png", map_type="cbf")

# Selecting a different LUT
rgb_gray   = apply_a_lut(cbf_map, map_type="cbf", lut="grayscale")
rgb_custom = apply_a_lut(cbf_map, map_type="cbf", lut="custom",
                         custom_lut_path="my_research_lut.csv")

# Using it with an existing matplotlib imshow
import matplotlib.pyplot as plt
cmap = to_mpl_colormap("asist")
plt.imshow(cbf_map, cmap=cmap, vmin=0, vmax=80)
```

---

## 7. Validation figures

Generator script: [`make_a_lut_figures.py`](make_a_lut_figures.py)

```bash
python make_a_lut_figures.py            # all five types (cbf/cbv/mtt/ttp/tmax)
python make_a_lut_figures.py cbf cbv    # only the named types
```

Written to `output/figures/a_lut/`. For each `map_type` there are five files:

| Suffix | Contents |
|---|---|
| `_grayscale.png` | the grayscale map |
| `_asist.png`     | the ASIST a-LUT map |
| `_histogram.png` | the value distribution with the display window (vmin/vmax) |
| `_colorbar.png`  | the colour bar, in the ASIST style |
| `_comparison.png`| grayscale and ASIST side by side, with the colour bar |

The input is `output/maps/<map_type>.npy` when that real data exists, and otherwise a
deterministic synthetic phantom, with an ischaemic core at the centre and a mask outside
the skull.

---

## 8. Unit tests

Tests: [`tests/test_a_lut_core.py`](tests/test_a_lut_core.py) (5 tests)

```bash
python -m pytest tests/test_a_lut_core.py -v   # with pytest
python tests/test_a_lut_core.py                # or the minimal runner, without pytest
```

What they check:

- deterministic RGB output for a fixed scalar value
- that quantitative voxel values are unchanged
- that the packaged LUT asset loads through `importlib.resources`
- the endpoints of the LUT, black at 0 and red at 255
- that the midpoint of the display window maps to index 128

---

## 9. A worked Methods paragraph for IORN-001

> **Perfusion map visualization.**
> Parametric perfusion maps (CBF, CBV, MTT, TTP, and Tmax) were rendered using
> the standardized lookup table (a-LUT) published by the Acute Stroke Imaging
> Standardization Group Japan (ASIST-Japan; CT/MR Perfusion Imaging Practical
> Guideline 2006). The a-LUT is a 256-level RGB table mapping low-to-high values
> from black through blue/cyan/green/yellow to red. Scalar maps were linearly
> windowed to standard display ranges (CBF 0-80 mL/100 g/min, CBV 0-8 mL/100 g,
> MTT 0-12 s, TTP 0-25 s, Tmax 0-14 s), normalized, and indexed into the a-LUT.
> Color mapping affects visualization only; quantitative voxel values were
> preserved unchanged and stored separately. The implementation is deterministic:
> identical scalar values yield bit-exact RGB output, verified by unit tests.
> Grayscale and custom research LUTs are also supported for comparison.

---

## 10. File list

| Path | Role |
|---|---|
| [`ctp_core/a_lut.py`](ctp_core/a_lut.py) | the a-LUT module itself |
| [`tests/test_a_lut_core.py`](tests/test_a_lut_core.py) | the unit tests (5) |
| [`make_a_lut_figures.py`](make_a_lut_figures.py) | the validation figure generator |
| `ctp_core/assets/alut.csv` | the ASIST standard a-LUT (the canonical source) |
| `ctp_core/assets/alut.tif`, `ctp_core/assets/ASIST.lut`, `ctp_core/assets/alut-horizontal.gif` | reference assets |
| `output/figures/a_lut/` | the generated validation figures |
