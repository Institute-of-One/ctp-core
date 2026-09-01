# -*- coding: utf-8 -*-
"""
ctp-core — open, reproducible CT Perfusion analysis core
========================================================

The reproducible analysis core for IORN-001. It provides the scientific logic alone
(NumPy and SciPy only), with no dependency on a graphical user interface, DICOM
input/output or any user interface, so that it can be released publicly on GitHub with a
Zenodo DOI and verified and reproduced independently.

Design boundary:
  - **ctp-core (this package)**: algorithms, numerical computation, visualization
    (the ASIST a-LUT), synthetic data generation and validation scripts. It does not
    depend on a GUI, tkinter or DICOM input/output.
  - **ctp-app (the graphical application)**: the DICOM workflow, the interactive viewer,
    batch processing and configuration. It *calls* ctp-core rather than duplicating its
    algorithms.

Migration policy (incremental and non-breaking):
  The scientific logic is moved into this package in stages. During the transition the
  older top-level modules (for example ``gamma_fit.py``) remain as backwards-compatible
  shims, so that the existing graphical application keeps working without a single
  import being changed.

Public API (extended as the migration proceeds):
  from ctp_core.gamma_fit import fit_gamma_variate, compute_indices_map
"""

from __future__ import annotations

# --- re-export the modules that have been moved in so far ---
from . import gamma_fit
from . import preprocessing
from . import tdc_analysis
from . import aif_detection
from . import parametric_maps
from . import synthetic
from . import a_lut

from .gamma_fit import (
    fit_gamma_variate,
    compute_raw_indices,
    compute_indices_map,
    GammaFitResult,
    gamma_variate,
)
from .preprocessing import PreprocessConfig, preprocess_slice, preprocess_curve
from .tdc_analysis import TDCData, TDCAnalyzer
from .aif_detection import AIFDetector, AIFResult
from .parametric_maps import ParametricMapGenerator, ParametricMaps
from .synthetic import generate_synthetic_tac, SyntheticTAC
from .a_lut import (
    load_a_lut, apply_a_lut, scalar_to_index,
    to_mpl_colormap, MAP_PRESETS,
)

__all__ = [
    # modules
    "gamma_fit", "preprocessing", "tdc_analysis",
    "aif_detection", "parametric_maps", "synthetic", "a_lut",
    # gamma fit
    "fit_gamma_variate", "compute_raw_indices", "compute_indices_map",
    "GammaFitResult", "gamma_variate",
    # preprocessing
    "PreprocessConfig", "preprocess_slice", "preprocess_curve",
    # tdc
    "TDCData", "TDCAnalyzer",
    # aif
    "AIFDetector", "AIFResult",
    # parametric maps
    "ParametricMapGenerator", "ParametricMaps",
    # synthetic data (IORN-001 validation)
    "generate_synthetic_tac", "SyntheticTAC",
    # ASIST a-LUT visualization
    "load_a_lut", "apply_a_lut", "scalar_to_index",
    "to_mpl_colormap", "MAP_PRESETS",
]

__version__ = "0.1.1"
