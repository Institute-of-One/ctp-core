# -*- coding: utf-8 -*-
"""
ctp-core 再現性デモ (IORN-001)
==============================

合成 CTP 時間–濃度曲線を生成し、ctp-core の gamma-variate フィットで
解析して、検証用の図とメトリクスを出力する **決定論的** デモ。

実行:
    python examples/run_synthetic_demo.py

出力:
    outputs/synthetic_fit_example.png   … クリーン/ノイズ/フィット曲線の図
    outputs/synthetic_metrics.json      … 真値・フィット値・誤差のメトリクス

GUI・DICOM・患者/顧客データには一切依存しない。
"""

from __future__ import annotations

import os
import sys
import json

import numpy as np

# examples/ から実行してもパッケージを解決できるようリポジトリ root を追加
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ctp_core.synthetic import generate_synthetic_tac
from ctp_core.gamma_fit import fit_gamma_variate, compute_raw_indices

OUT_DIR = os.path.join(_REPO_ROOT, "outputs")


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    # --- 1. 合成 CTP 曲線を生成 (固定シードで完全再現) ---
    # 検証デモ: 単一ボーラス + SNR=20 ノイズ。真値パラメータの回復精度を示す。
    # (再循環成分は ctp_core.synthetic の機能としてテスト側で別途検証する)
    tac = generate_synthetic_tac(
        amplitude=60.0, t0=8.0, alpha=3.0, beta=2.0,
        n_time_points=40, dt=1.0, snr=20.0,
        recirculation=False, seed=0,
    )
    gt = tac.ground_truth

    # --- 2. ctp-core で gamma-variate フィット ---
    fit = fit_gamma_variate(tac.time, tac.noisy)

    # --- 3. ピーク時刻・ピーク値 (フィット由来 + raw 検出) ---
    raw = compute_raw_indices(tac.time, tac.noisy)

    # --- 4. 派生パラメータ (フィット結果) ---
    derived = {
        "fit_success": bool(fit.success),
        "K": fit.K, "t0": fit.t0, "alpha": fit.alpha, "beta": fit.beta,
        "peak_value": fit.peak_value, "peak_time": fit.peak_time,
        "auc": fit.auc, "bat": fit.bat,
        "r_squared": fit.r_squared, "rmse": fit.rmse,
    }

    # 真値との誤差 (再現性検証の核)
    errors = {
        "peak_time_abs_err": abs(fit.peak_time - gt["true_peak_time"]),
        "peak_value_abs_err": abs(fit.peak_value - gt["true_peak_value"]),
        "bat_abs_err": abs(fit.bat - gt["true_bat"]),
    }

    # --- 5. 図を保存 ---
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(tac.time, tac.noisy, "o", ms=4, color="0.5",
            label="noisy (SNR=%.0f)" % gt["snr"] if np.isfinite(gt["snr"]) else "noisy")
    ax.plot(tac.time, tac.clean, "-", lw=1.5, color="tab:blue",
            label="clean (ground truth)")
    if fit.success and fit.fitted_curve is not None:
        ax.plot(tac.time, fit.fitted_curve, "--", lw=2, color="tab:red",
                label="ctp-core fit (R²=%.3f)" % fit.r_squared)
        ax.axvline(fit.peak_time, color="tab:red", ls=":", lw=1)
        ax.plot([fit.peak_time], [fit.peak_value], "x", color="tab:red", ms=10)
    ax.axvline(gt["true_peak_time"], color="tab:blue", ls=":", lw=1)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Enhancement (a.u.)")
    ax.set_title("ctp-core synthetic gamma-variate fit (IORN-001 demo)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig_path = os.path.join(OUT_DIR, "synthetic_fit_example.png")
    fig.savefig(fig_path, dpi=150)
    plt.close(fig)

    # --- 6. メトリクスを JSON 保存 + サマリ表示 ---
    metrics = {
        "ground_truth": gt,
        "raw_detection": raw,
        "fit_derived": derived,
        "errors_vs_ground_truth": errors,
    }
    json_path = os.path.join(OUT_DIR, "synthetic_metrics.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print("=== ctp-core synthetic demo (IORN-001) ===")
    print(f"ground truth : peak_time={gt['true_peak_time']:.2f}s  "
          f"peak={gt['true_peak_value']:.2f}  bat={gt['true_bat']:.2f}s")
    print(f"ctp-core fit : peak_time={fit.peak_time:.2f}s  "
          f"peak={fit.peak_value:.2f}  bat={fit.bat:.2f}s  R2={fit.r_squared:.4f}")
    print(f"raw detect   : ttp={raw['ttp']:.2f}s  peak={raw['peak']:.2f}")
    print(f"abs errors   : peak_time={errors['peak_time_abs_err']:.3f}s  "
          f"peak={errors['peak_value_abs_err']:.3f}  bat={errors['bat_abs_err']:.3f}s")
    print(f"saved figure : {fig_path}")
    print(f"saved metrics: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
