# ctp-core

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20921268.svg)](https://doi.org/10.5281/zenodo.20921268)

**Open, reproducible CT Perfusion analysis core — IORN-001**

`ctp-core` is the open, reproducible scientific core of a CT Perfusion (CTP)
analysis pipeline. It exposes the numerical algorithms and standardized
visualization needed to **independently reproduce and validate** CTP-derived
parameters, with no graphical application, no DICOM I/O, and no confidential
data.

> This package is the *reproducible core* referenced by **IORN-001**
> (Institute of One Reproducible Note 001). The full interactive GUI
> application is a separate, private project and is **not included here**.

---

## Purpose

- Provide transparent, testable implementations of CTP analysis:
  - gamma-variate fitting
  - baseline correction / preprocessing
  - peak detection and derived parameters (TTP, Peak, AUC, BAT)
  - parametric maps (CBF / CBV / MTT via SVD deconvolution)
- Provide a **reproducible synthetic data generator** for validation.
- Provide **ASIST-Japan standard a-LUT** perfusion color mapping
  (visualization only; quantitative values are never altered).
- Ship with tests, a CLI example, and documentation for publication
  (GitHub + Zenodo DOI) and citation.

## What is **not** included

- ❌ The private GUI software (ctp-app): Canvas / PyWebView / interactive viewer.
- ❌ DICOM I/O / patient-data workflow.
- ❌ Any confidential, client, or patient data.

All example data are **synthetically generated** and contain no real subjects.

---

## Installation

Requires Python 3.9+.

```bash
pip install -r requirements-core.txt
```

Core runtime dependencies: `numpy`, `scipy`, `matplotlib`
(see [`requirements-core.txt`](requirements-core.txt)).

---

## Reproducibility demo

Generate synthetic CTP curves, fit them with `ctp-core`, and write a figure
plus metrics:

```bash
python examples/run_synthetic_demo.py
```

Outputs (deterministic):

```text
outputs/synthetic_fit_example.png   # clean / noisy / fitted curves
outputs/synthetic_metrics.json      # ground truth, fit, and absolute errors
```

---

## API example

```python
import numpy as np
from ctp_core.synthetic import generate_synthetic_tac
from ctp_core.gamma_fit import fit_gamma_variate, compute_raw_indices
from ctp_core.a_lut import apply_a_lut

# 1. Reproducible synthetic time–attenuation curve
tac = generate_synthetic_tac(amplitude=60, t0=8, alpha=3, beta=2,
                             snr=20, n_time_points=40, dt=1.0, seed=0)

# 2. Gamma-variate fit (derived parameters are analytic)
fit = fit_gamma_variate(tac.time, tac.noisy)
print(fit.summary_line())          # Peak / TTP / BAT / AUC / R^2

# 3. Raw (no-fit) peak detection
raw = compute_raw_indices(tac.time, tac.noisy)   # {'ttp','peak','auc','bat'}

# 4. ASIST a-LUT visualization (quantitative values unchanged)
cbf_map = np.random.default_rng(0).uniform(0, 80, size=(64, 64))
rgb = apply_a_lut(cbf_map, map_type="cbf")        # (H, W, 3) uint8
```

The ASIST-Japan standard LUT is packaged at `ctp_core/assets/alut.csv` and is
resolved via `importlib.resources` (an explicit `path=` override is also
supported). LUTs affect **visualization only**; quantitative voxel values are
preserved.

---

## Tests

```bash
python -m pytest tests/ -q          # or: python tests/test_gamma_fit.py
```

Tests cover synthetic curve generation, fitting (finite parameters, ground-truth
recovery), peak detection, derived parameters, public-API import, and
deterministic a-LUT RGB output. They depend on neither the GUI nor DICOM nor
any private data.

---

## Package layout

```text
ctp_core/                 open reproducible core (this package)
  gamma_fit.py            gamma-variate fitting + derived indices
  preprocessing.py        baseline correction / smoothing
  tdc_analysis.py         time-density curve analysis
  aif_detection.py        arterial input function detection
  parametric_maps.py      CBF / CBV / MTT (SVD deconvolution)
  synthetic.py            reproducible synthetic TAC generator
  a_lut.py                ASIST-Japan standard a-LUT visualization
  assets/alut.csv         packaged ASIST standard LUT
examples/run_synthetic_demo.py
tests/
```

---

## Citation

If you use this software, please cite it via [`CITATION.cff`](CITATION.cff).

- Author: Shuji Yamamoto — Institute of One
- ORCID: [0000-0001-9211-1071](https://orcid.org/0000-0001-9211-1071)
- Reference: IORN-001
- DOI (all versions / concept): [10.5281/zenodo.20921268](https://doi.org/10.5281/zenodo.20921268)
- DOI (this release, v0.1.0): [10.5281/zenodo.20921269](https://doi.org/10.5281/zenodo.20921269)

## License

[MIT](LICENSE) © 2026 Shuji Yamamoto (Institute of One)
