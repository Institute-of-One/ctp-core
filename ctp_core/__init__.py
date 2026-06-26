# -*- coding: utf-8 -*-
"""
ctp-core — open, reproducible CT Perfusion analysis core
========================================================

IORN-001 のための再現可能な解析コア。GUI/DICOM/UI に依存しない純粋な
科学ロジック (numpy/scipy のみ) を提供し、GitHub / Zenodo DOI 公開、
および独立した検証・再現を可能にする。

設計境界:
  - **ctp-core (本パッケージ)**: アルゴリズム・数値計算・可視化 (ASIST a-LUT)・
    合成データ生成・検証スクリプト。GUI/tkinter/DICOM I/O には依存しない。
  - **ctp-app (GUI アプリ)**: DICOM ワークフロー・インタラクティブビューア・
    バッチ・設定など実用機能。ctp-core を *呼び出す* (アルゴリズムを複製しない)。

移行方針 (段階的・非破壊):
  科学ロジックは段階的に本パッケージへ移設する。移行期間中は旧トップレベル
  モジュール (例: ``gamma_fit.py``) を後方互換 shim として残し、既存 GUI の
  import を一切変更せずに動作させる。

公開 API (順次拡張):
  from ctp_core.gamma_fit import fit_gamma_variate, compute_indices_map
"""

from __future__ import annotations

# --- 移設済みモジュールの再エクスポート (順次追加) ---
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

__version__ = "0.1.0"
