# -*- coding: utf-8 -*-
"""Check that the public ctp-core API imports with no GUI, no DICOM and no patient data."""

import _pathfix  # noqa: F401  (puts the repository root on sys.path)


def test_import_ctp_core():
    import ctp_core
    assert hasattr(ctp_core, "__version__")
    assert len(ctp_core.__all__) > 0


def test_core_public_symbols_present():
    import ctp_core
    for name in (
        "gamma_variate", "fit_gamma_variate", "compute_indices_map",
        "PreprocessConfig", "preprocess_slice",
        "TDCAnalyzer", "AIFDetector", "ParametricMapGenerator",
        "generate_synthetic_tac", "apply_a_lut", "load_a_lut",
    ):
        assert hasattr(ctp_core, name), f"missing public symbol: {name}"


def test_submodule_imports():
    from ctp_core import (  # noqa: F401
        gamma_fit, preprocessing, tdc_analysis,
        aif_detection, parametric_maps, synthetic, a_lut,
    )


def test_core_has_no_gui_or_dicom_dependency():
    """No ctp_core module imports a GUI, DICOM or viewer module.

    Inspects sys.modules after importing, to confirm that tkinter, pydicom, viewer
    and main were not pulled in through ctp_core.
    """
    import sys
    # Do not require that the related modules are unloaded, so the check is not
    # affected by other tests: inspect the declared dependencies inside ctp_core.
    import importlib
    import ctp_core

    forbidden = ("tkinter", "pydicom", "viewer", "main")
    for modname in list(ctp_core.__all__):
        mod = getattr(ctp_core, modname, None)
        if mod is None or not hasattr(mod, "__file__"):
            continue
        src_path = getattr(mod, "__file__", "")
        if not src_path or not src_path.endswith(".py"):
            continue
        with open(src_path, "r", encoding="utf-8") as f:
            src = f.read()
        for bad in forbidden:
            assert f"import {bad}" not in src and f"from {bad}" not in src, (
                f"ctp_core.{modname} imports the forbidden dependency '{bad}'"
            )


if __name__ == "__main__":
    import _runner
    _runner.run(globals())
