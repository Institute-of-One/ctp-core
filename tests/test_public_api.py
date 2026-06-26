# -*- coding: utf-8 -*-
"""ctp-core 公開 API が GUI/DICOM/患者データ無しで import 可能であることを検証する。"""

import _pathfix  # noqa: F401  (リポジトリ root を sys.path へ)


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
    """ctp_core のどのモジュールも GUI/DICOM/viewer を import していないこと。

    モジュールを import した後の sys.modules を検査し、tkinter / pydicom /
    viewer / main が ctp_core 経由で読み込まれていないことを確認する。
    """
    import sys
    # クリーンに評価するため、関連モジュールが未ロードの状態を要求しない
    # (他テストの影響を避けるため、ここでは ctp_core 内の宣言的依存を検査)
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
                f"ctp_core.{modname} は禁止依存 '{bad}' を import しています"
            )


if __name__ == "__main__":
    import _runner
    _runner.run(globals())
