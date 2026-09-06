"""Create an illustrative ctp-core figure from the public UniToBrain CTP data.

This script is submission support, not part of the ctp_core public API. It expects
the extracted UniToBrain test case MOL-001 and uses the repository DICOM loader to
convert DICOM files to the (time, slice, row, column) array accepted by ctp_core.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT))

from ctp_core.aif_detection import AIFDetector  # noqa: E402
from ctp_core.gamma_fit import fit_gamma_variate  # noqa: E402
from ctp_core.parametric_maps import ParametricMapGenerator  # noqa: E402
from dicom_loader import load_perfusion_dicom  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--slice", type=int, default=8, dest="slice_index")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("figure_unitobrain_mol001.png"),
    )
    args = parser.parse_args()

    volume, metadata = load_perfusion_dicom(str(args.case_dir))
    slice_index = args.slice_index
    if not 0 <= slice_index < metadata["n_slices"]:
        raise ValueError(f"slice must be 0..{metadata['n_slices'] - 1}")

    aif = AIFDetector(volume, metadata).detect(slice_index=slice_index)
    if aif.aif_curve is None or aif.n_aif_voxels == 0:
        raise RuntimeError("AIF detection did not return a usable curve")

    baseline = volume[:2, slice_index].mean(axis=0)
    peak_enhancement = (volume[:, slice_index] - baseline).max(axis=0)
    brain_mask = (baseline > 0) & (baseline < 100) & (peak_enhancement > 5)
    maps = ParametricMapGenerator(volume, metadata).compute(
        aif.aif_curve,
        slice_index=slice_index,
        n_baseline=2,
        method="circulant",
        svd_threshold=0.15,
        brain_mask=brain_mask,
    )

    time = np.asarray(metadata["time_seconds"], dtype=float)
    enhancement = np.asarray(aif.aif_enhancement, dtype=float)
    fit = fit_gamma_variate(time, enhancement, min_peak_value=5.0)

    fig, axes = plt.subplots(2, 3, figsize=(12.4, 7.5), constrained_layout=True)
    ax = axes[0, 0]
    ax.imshow(baseline, cmap="gray", vmin=0, vmax=80)
    if aif.aif_center is not None:
        row, col = aif.aif_center
        ax.plot(col, row, "o", ms=11, mfc="none", mec="#ffcc00", mew=2)
    ax.set_title("A  Baseline CT and detected AIF")

    ax = axes[0, 1]
    ax.plot(time, enhancement, "o", color="#1967a3", label="Detected AIF")
    if fit.success:
        ax.plot(time, fit.fitted_curve, "-", color="#d1495b", lw=2, label="Gamma-variate fit")
    ax.set(xlabel="Time (s)", ylabel="Enhancement (HU)", title="B  Arterial input function")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=8)

    panels = [
        (axes[0, 2], maps.cbf, "C  CBF", "ml/100 g/min", 0, 100),
        (axes[1, 0], maps.cbv, "D  CBV", "ml/100 g", 0, 8),
        (axes[1, 1], maps.mtt, "E  MTT", "s", 0, 15),
        (axes[1, 2], maps.ttp, "F  TTP", "s", 0, float(time[-1])),
    ]
    for map_ax, data, title, unit, vmin, vmax in panels:
        masked = np.ma.masked_where(~brain_mask, data)
        map_ax.imshow(baseline, cmap="gray", vmin=0, vmax=80)
        image = map_ax.imshow(masked, cmap="turbo", vmin=vmin, vmax=vmax, alpha=0.82)
        map_ax.set_title(title)
        fig.colorbar(image, ax=map_ax, shrink=0.78, pad=0.02, label=unit)

    for item in axes.flat:
        if item is not axes[0, 1]:
            item.set_xticks([])
            item.set_yticks([])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    summary = {
        "source": "UniToBrain v1.4, test case MOL-001",
        "doi": "10.5281/zenodo.5109415",
        "shape": list(volume.shape),
        "time_seconds": metadata["time_seconds"],
        "slice_index": slice_index,
        "slice_position_mm": metadata["slice_positions"][slice_index],
        "aif_center_row_col": list(aif.aif_center) if aif.aif_center else None,
        "aif_voxels": int(aif.n_aif_voxels),
        # Quoted in Section 3.4 of the manuscript, so it is recorded here rather than
        # left to be read off the plot.
        "aif_peak_enhancement_hu": float(np.max(enhancement)),
        "gamma_fit_success": bool(fit.success),
        "gamma_fit_r_squared": float(fit.r_squared) if fit.success else None,
        "processed_pixels": maps.computation_info["processed_pixels"],
        "svd_method": maps.computation_info["method"],
        "svd_threshold": maps.computation_info["svd_threshold"],
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
