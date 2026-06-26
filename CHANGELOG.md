# Changelog

All notable changes to **ctp-core** are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
