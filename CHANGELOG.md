# Changelog

All notable changes to **ctp-core** are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-20

The release the British Journal of Radiology submission describes. Nothing in `ctp_core/`
changed: this adds the measurement made *with* it, and the code that made it.

### Added
- **`paper/analysis/` — every number in the manuscript, and the code that produced it.**
  `ctp_measure.py` holds the measurement logic (the validity rule, the quantisation floor,
  the positive-area integral, the CBV ratio, the hemispheric split); `unitobrain.py` is the
  only module that knows the dataset's layout; six drivers write the files in
  `paper/results/`. They were in a scratch directory while the measurements were designed,
  which put them outside version control and outside review.
- **`paper/PROTOCOL.md` — the design, frozen before implementation, with every amendment
  dated and reasoned.** Thirteen of them, including the two that changed what is reported:
  the precision of the clinical sampling rule was overstated by an order of magnitude, and
  part of the agreement with the reference maps was the measurement's own sampling noise.
- **`paper/results/` — the measured values as data files**, which the figures and the
  manuscript are generated from, so no number in the paper is typed by hand.
- `paper/make_figures.py`, `paper/build_manuscript.py`, `paper/references.py` and the
  submission assembly, with their checkers: `check_manuscript.py`, `check_references.py`
  and two scripts that prove those checkers by breaking a manuscript seventeen ways and a
  reference list six, requiring each to be rejected.
- `paper/verify_release.py` — exports the tree as the archive will ship it, installs the
  declared dependencies into an empty virtual environment, and runs the paths the data
  availability statement promises. This is the check whose absence let v0.1.0 be cited by
  DOI while it no longer ran.
- `.ai-check/` — six rounds of independent review by two models, their findings, and what
  was done about each. Thirty-one defects; the measured values did not move after the third
  round.
- Two more CI jobs: the measurement suite with its injection proof, and the manuscript
  pipeline with its own.

### Changed
- `tests/test_release_metadata.py` now also requires the four files that carry the version
  to agree, refuses a top-level `doi` in `.zenodo.json`, and recognises the window between
  bumping a version and the DOI being minted instead of either failing or passing blindly.

### Fixed
- The data availability statement pointed at "the digital object identifier given on the
  title page", and the title page gave none.

## [0.1.1] - 2026-09-01

### Fixed
- **`ctp_core/parametric_maps.py` no longer fails on NumPy 2.** `np.trapz` was removed in
  NumPy 2.0 and was called at two sites on the CBF/CBV/MTT/TTP path. Because
  `requirements-core.txt` carries no upper bound on NumPy, a fresh install raised
  `AttributeError: module 'numpy' has no attribute 'trapz'` as soon as parametric maps
  were computed. The calls now resolve to `np.trapezoid` where it exists and fall back to
  `np.trapz` on NumPy 1.x. Numerical results are unchanged.

### Added
- `tests/test_parametric_maps.py` — the first tests for the parametric-map module, whose
  absence is why the defect above was invisible. They exercise the trapezoidal integral
  rather than only importing the module, assert that every masked pixel is really
  processed (the loop swallows per-pixel exceptions and would otherwise return silent
  zeros), and scan the package for every attribute NumPy 2.0 removed.
- `.github/workflows/tests.yml` is now committed, so continuous integration actually runs
  the suite and both examples on Python 3.9 and 3.12.

### Changed
- **The package is now documented in English.** Every docstring, comment and runtime
  message in `ctp_core/`, `examples/`, `tests/` and `make_a_lut_figures.py` was
  translated; no code was altered, which was verified by comparing the abstract syntax
  tree of every file before and after.
- `A_LUT.md` translated, its three dead links repaired (`a_lut.py` and `test_a_lut.py`
  do not exist; the files are `ctp_core/a_lut.py` and `tests/test_a_lut_core.py`) and its
  test count corrected from 29 to 5.
- Author affiliation given in full as
  "Institute of One, LISIT Co., Ltd., Tokyo 150-0044, Japan", matching the Crossref
  record of the author's published work.
- `CITATION.cff` now carries the Zenodo **concept** DOI; the paper cites the version DOI.

### Maintenance
- 2026-08-01: Updated author affiliation in `CITATION.cff`, `.zenodo.json`, and
  `README.md`; normalized `ctp_core/assets/alut.csv` line endings to LF; added
  `RESUME.md` (private notes) to `.gitignore`.

### Added
- `ctp_core/synthetic.py` — reproducible synthetic CT Perfusion time–attenuation
  curve generator (gamma-variate based; fixed-seed, configurable amplitude / t0 /
  alpha / beta / SNR / sampling / optional recirculation; returns time, clean,
  noisy, and ground-truth parameters).
- `examples/run_synthetic_demo.py` — deterministic reproducibility demo:
  generate → fit (ctp-core) → peak/derived parameters → figure + metrics
  (`outputs/synthetic_fit_example.png`, `outputs/synthetic_metrics.json`).
- `tests/` — core test suite (public API, synthetic generator, gamma-variate
  fitting / peak detection / derived parameters, ASIST a-LUT deterministic RGB).
- Publication skeleton: `README.md`, `LICENSE` (MIT), `CITATION.cff`,
  `requirements-core.txt`, `CHANGELOG.md`.
- ASIST a-LUT asset packaged at `ctp_core/assets/alut.csv`, resolved via
  `importlib.resources` with a `__file__` fallback; explicit `path` override
  preserved. Visualization-only; quantitative voxel values unchanged.

### Changed
- Migrated pure scientific modules into the `ctp_core` package:
  `gamma_fit`, `preprocessing`, `tdc_analysis`, `aif_detection`,
  `parametric_maps`, `a_lut`. Backward-compatible shims remain at the old
  top-level paths so the existing GUI app imports are unchanged.

### Notes
- The private GUI application (ctp-app) and DICOM I/O are intentionally **not**
  part of the open core.
- No confidential, client, or patient data are included.

## [0.1.0] — 2026-06-25
- Initial extraction of the reproducible core (`ctp_core`) from the CT
  Perfusion Analyzer application, with backward-compatible shims.
