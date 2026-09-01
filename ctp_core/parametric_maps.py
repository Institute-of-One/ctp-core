"""
Parametric map generation
====================================
Generates CBF, CBV, MTT and TTP maps using an arterial input function and
deconvolution analysis.

Theoretical background:
---------
The basic CT-perfusion model (the indicator-dilution theory of Meier & Zierler, 1954):

    C_tissue(t) = CBF * (C_a(t) ⊗ R(t))

where:
    C_tissue(t): contrast concentration in tissue (enhancement)
    C_a(t): the arterial input function (AIF)
    R(t): the residue function
    (*): convolution

References:
- Ostergaard L, et al. "High resolution measurement of cerebral
  blood flow using intravascular tracer bolus passages. Part I:
  Mathematical approach and statistical analysis."
  Magnetic Resonance in Medicine. 1996;36(5):715-725.
  -> the original description of SVD deconvolution:
    "The tissue concentration time curve C(t) can be expressed as
     C(t) = CBF · (Ca(t) ⊗ R(t)), where R(t) is the residue
     function describing the fraction of tracer still present in
     the tissue at time t."
    "CBF is determined as the maximum of the deconvolved residue
     function: CBF = max(R(t))"

- Wu O, et al. "Tracer arrival timing-insensitive technique for
  estimating flow in MR perfusion-weighted imaging using singular
  value decomposition with a block-circulant deconvolution matrix."
  Magnetic Resonance in Medicine. 2003;50(1):164-174.
  -> delay-insensitive deconvolution by block-circulant SVD (oSVD):
    "By using a block-circulant matrix formulation, the technique
     becomes insensitive to tracer arrival timing differences
     between the AIF and tissue curves."

- Konstas AA, et al. "Theoretic basis and technical implementations
  of CT perfusion in acute ischemic stroke, Part 1: Theoretic basis."
  AJNR American Journal of Neuroradiology. 2009;30(4):662-668.
  -> a comprehensive review of the theoretical basis of CT perfusion:
    "CBV is proportional to the area under the tissue enhancement
     curve: CBV = (1/ρ) · ∫C_tissue(t)dt / ∫C_a(t)dt"
    "MTT = CBV / CBF (central volume theorem)"

Usage:
    from parametric_maps import ParametricMapGenerator
    generator = ParametricMapGenerator(volume_4d, metadata)
    maps = generator.compute(aif_curve, slice_index=2)
    generator.save_maps(maps, "output_folder")
"""

import numpy as np
from scipy.linalg import svd, circulant


class ParametricMaps:
    """Holds the result of parametric map generation."""

    def __init__(self):
        self.cbf = None   # Cerebral Blood Flow map (ml/100g/min)
        self.cbv = None   # Cerebral Blood Volume map (ml/100g)
        self.mtt = None   # Mean Transit Time map (s)
        self.ttp = None   # Time to Peak map (s)
        self.tmax = None  # Time to Maximum of residue function (s)
        self.delay = None # Tracer arrival delay map (s)
        self.residue = None  # residue function map (n_times, rows, cols)
        self.slice_index = None
        self.computation_info = {}


class ParametricMapGenerator:
    """The parametric map generation engine."""

    # Conversion factor from CT number to contrast concentration
    # (Wintermark et al., 2005: about 1 HU ~ 1 mg/mL for iodinated contrast)
    HU_TO_CONCENTRATION = 1.0

    # Density of brain tissue (g/mL)
    BRAIN_DENSITY = 1.04

    def __init__(self, volume_4d, metadata):
        self.volume = volume_4d
        self.meta = metadata
        self.n_times = metadata['n_times']
        self.rows = metadata['rows']
        self.cols = metadata['cols']
        self.time_seconds = np.array(metadata['time_seconds'])

        # Compute the sampling interval
        if len(self.time_seconds) > 1:
            self.dt = np.mean(np.diff(self.time_seconds))
        else:
            self.dt = 1.0

    def _build_convolution_matrix(self, aif, method='standard'):
        """Build the convolution matrix from the AIF.

        Standard SVD:
            a lower-triangular Toeplitz matrix
            (Ostergaard 1996: standard truncated SVD)

        Block-circulant SVD (oSVD):
            uses a block-circulant matrix, which is robust to delay
            (Wu 2003: block-circulant deconvolution)

        Args:
            aif: the AIF enhancement curve (n_times,)
            method: 'standard' or 'circulant'

        Returns:
            A: the convolution matrix, shape (N, N) or (2N, 2N)
        """
        n = len(aif)

        if method == 'standard':
            # The standard lower-triangular Toeplitz matrix
            A = np.zeros((n, n))
            for i in range(n):
                for j in range(i + 1):
                    A[i, j] = aif[i - j]
            A *= self.dt
            return A

        elif method == 'circulant':
            # Block-circulant matrix (Wu 2003)
            # Build the 2N x 2N circulant matrix
            D = 2 * n
            c = np.zeros(D)
            c[:n] = aif
            # A circulant matrix is generated from its first column
            A = circulant(c) * self.dt
            return A

        else:
            raise ValueError(f"Unknown method: {method}")

    def _svd_deconvolution(self, tissue_curve, aif, method='circulant',
                            svd_threshold=0.15):
        """Run the SVD deconvolution.

        The truncated SVD method of Ostergaard (1996):
        1. C_tissue = CBF * dt * A * R  (A: the convolution matrix of the AIF)
        2. R = (1/CBF) * A^(-1) * C_tissue / dt
        3. invert A, regularized by the SVD

        Args:
            tissue_curve: the tissue enhancement curve
            aif: the AIF enhancement curve
            method: 'standard' or 'circulant'
            svd_threshold: singular-value cutoff, as a fraction of the largest one
                          (Ostergaard 1996: "singular values below a threshold
                           fraction of the maximum singular value are set to zero")

        Returns:
            residue: the residue function R(t)
            cbf: the CBF value
        """
        n = len(aif)

        # Build the convolution matrix
        A = self._build_convolution_matrix(aif, method=method)

        if method == 'circulant':
            # The input vector is extended to 2N as well
            tissue_ext = np.zeros(2 * n)
            tissue_ext[:n] = tissue_curve
        else:
            tissue_ext = tissue_curve

        # SVD decomposition
        U, S, Vt = svd(A, full_matrices=False)

        # Truncate the singular values (regularization)
        # (Ostergaard 1996: truncated SVD)
        s_max = S[0]
        threshold = svd_threshold * s_max
        S_inv = np.zeros_like(S)
        for i, s in enumerate(S):
            if s > threshold:
                S_inv[i] = 1.0 / s

        # Compute the residue function
        # R = V * diag(1/S) * U^T * C_tissue
        residue_full = Vt.T @ np.diag(S_inv) @ U.T @ tissue_ext

        if method == 'circulant':
            residue = residue_full[:n]
        else:
            residue = residue_full

        # CBF = max(R(t))
        # (Ostergaard 1996: "CBF is determined as the maximum of
        #  the deconvolved residue function")
        cbf = np.max(residue)

        return residue, cbf

    def compute(self, aif_curve, slice_index, n_baseline=2,
                method='circulant', svd_threshold=0.15,
                brain_mask=None):
        """Compute the parametric maps.

        Args:
            aif_curve: the AIF enhancement curve (n_times,), as raw CT numbers
            slice_index: index of the slice to process
            n_baseline: number of baseline time points
            method: the deconvolution method
            svd_threshold: the SVD regularization threshold
            brain_mask: the brain mask; computed automatically when None

        Returns:
            ParametricMaps
        """
        maps = ParametricMaps()
        maps.slice_index = slice_index

        # Convert to enhancement
        slice_data = self.volume[:, slice_index, :, :]
        baseline = np.mean(slice_data[:n_baseline], axis=0)
        tissue_enhancement = slice_data - baseline[np.newaxis, :, :]

        aif_baseline = np.mean(aif_curve[:n_baseline])
        aif_enhancement = aif_curve - aif_baseline

        # Check that the AIF carries a usable value
        if np.max(aif_enhancement) <= 0:
            raise ValueError("The AIF enhancement is invalid (peak <= 0).")

        # Generate the brain mask automatically (a simple version)
        if brain_mask is None:
            peak_enh = np.max(tissue_enhancement, axis=0)
            brain_mask = (baseline > -10) & (baseline < 200) & (peak_enh > 5)

        # Initialize the maps
        cbf_map = np.zeros((self.rows, self.cols), dtype=np.float32)
        cbv_map = np.zeros((self.rows, self.cols), dtype=np.float32)
        mtt_map = np.zeros((self.rows, self.cols), dtype=np.float32)
        ttp_map = np.zeros((self.rows, self.cols), dtype=np.float32)
        tmax_map = np.zeros((self.rows, self.cols), dtype=np.float32)
        residue_map = np.zeros((self.n_times, self.rows, self.cols),
                                dtype=np.float32)

        # AIF area, used to compute CBV
        # (Konstas 2009: "CBV = (1/ρ) · ∫C_tissue(t)dt / ∫C_a(t)dt")
        trapezoid = np.trapezoid if hasattr(np, 'trapezoid') else np.trapz
        aif_area = trapezoid(aif_enhancement, self.time_seconds)
        if aif_area <= 0:
            aif_area = 1.0  # guard against division by zero

        # Deconvolution, pixel by pixel
        total_pixels = int(brain_mask.sum())
        processed = 0
        print_interval = max(total_pixels // 10, 1)

        print(f"Computing parametric maps... ({total_pixels} pixels)")

        for r in range(self.rows):
            for c in range(self.cols):
                if not brain_mask[r, c]:
                    continue

                tissue_curve = tissue_enhancement[:, r, c]

                # Skip pixels with little enhancement
                if np.max(tissue_curve) < 5:
                    continue

                try:
                    # SVD deconvolution
                    residue, cbf = self._svd_deconvolution(
                        tissue_curve, aif_enhancement,
                        method=method, svd_threshold=svd_threshold
                    )

                    # CBF, converted to ml/100 g/min
                    # CBF_raw is in 1/s, so multiply by 60 and scale to 100 g
                    cbf_value = cbf * 60.0 / self.BRAIN_DENSITY * 100.0

                    # CBV (ml/100g)
                    tissue_area = trapezoid(tissue_curve, self.time_seconds)
                    cbv_value = (tissue_area / aif_area) / self.BRAIN_DENSITY * 100.0

                    # MTT (s) = CBV / CBF, the central volume theorem
                    # (Konstas 2009: "MTT = CBV / CBF")
                    if cbf_value > 0:
                        mtt_value = cbv_value / cbf_value * 60.0
                    else:
                        mtt_value = 0.0

                    # TTP
                    ttp_idx = np.argmax(tissue_curve)
                    ttp_value = self.time_seconds[ttp_idx]

                    # Tmax: the time of the peak of the residue function
                    tmax_idx = np.argmax(residue)
                    tmax_value = self.time_seconds[min(tmax_idx, self.n_times - 1)]

                    # Clip the values, excluding outliers
                    cbf_map[r, c] = np.clip(cbf_value, 0, 150)
                    cbv_map[r, c] = np.clip(cbv_value, 0, 20)
                    mtt_map[r, c] = np.clip(mtt_value, 0, 30)
                    ttp_map[r, c] = ttp_value
                    tmax_map[r, c] = tmax_value
                    residue_map[:, r, c] = residue[:self.n_times]

                except Exception:
                    continue

                processed += 1
                if processed % print_interval == 0:
                    pct = processed / total_pixels * 100
                    print(f"  {pct:.0f}% ({processed}/{total_pixels})")

        print(f"  done: {processed} pixels processed")

        maps.cbf = cbf_map
        maps.cbv = cbv_map
        maps.mtt = mtt_map
        maps.ttp = ttp_map
        maps.tmax = tmax_map
        maps.residue = residue_map

        maps.computation_info = {
            'method': method,
            'svd_threshold': svd_threshold,
            'n_baseline': n_baseline,
            'dt': self.dt,
            'aif_area': float(aif_area),
            'processed_pixels': processed,
            'total_pixels': total_pixels,
        }

        return maps

    @staticmethod
    def save_maps(maps, output_folder):
        """Save the parametric maps as NumPy files."""
        import os
        os.makedirs(output_folder, exist_ok=True)

        np.save(os.path.join(output_folder, 'cbf_map.npy'), maps.cbf)
        np.save(os.path.join(output_folder, 'cbv_map.npy'), maps.cbv)
        np.save(os.path.join(output_folder, 'mtt_map.npy'), maps.mtt)
        np.save(os.path.join(output_folder, 'ttp_map.npy'), maps.ttp)
        np.save(os.path.join(output_folder, 'tmax_map.npy'), maps.tmax)

        print(f"Parametric maps saved: {output_folder}")


def plot_parametric_maps(maps, baseline_image=None, save_path=None):
    """Display the parametric maps."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle("CT Perfusion Parametric Maps", fontsize=16, fontweight='bold')

    # CBF
    ax = axes[0, 0]
    im = ax.imshow(maps.cbf, cmap='jet', vmin=0, vmax=100)
    plt.colorbar(im, ax=ax, label='ml/100g/min')
    ax.set_title('CBF (Cerebral Blood Flow)')

    # CBV
    ax = axes[0, 1]
    im = ax.imshow(maps.cbv, cmap='jet', vmin=0, vmax=10)
    plt.colorbar(im, ax=ax, label='ml/100g')
    ax.set_title('CBV (Cerebral Blood Volume)')

    # MTT
    ax = axes[0, 2]
    im = ax.imshow(maps.mtt, cmap='jet', vmin=0, vmax=20)
    plt.colorbar(im, ax=ax, label='seconds')
    ax.set_title('MTT (Mean Transit Time)')

    # TTP
    ax = axes[1, 0]
    im = ax.imshow(maps.ttp, cmap='jet')
    plt.colorbar(im, ax=ax, label='seconds')
    ax.set_title('TTP (Time to Peak)')

    # Tmax
    ax = axes[1, 1]
    im = ax.imshow(maps.tmax, cmap='jet')
    plt.colorbar(im, ax=ax, label='seconds')
    ax.set_title('Tmax (Time to Maximum)')

    # The baseline image, if there is one
    ax = axes[1, 2]
    if baseline_image is not None:
        ax.imshow(baseline_image, cmap='gray', vmin=0, vmax=100)
        ax.set_title('Baseline Image')
    else:
        ax.axis('off')
        info_text = (
            f"Computation Info:\n"
            f"  Method: {maps.computation_info.get('method', 'N/A')}\n"
            f"  SVD threshold: {maps.computation_info.get('svd_threshold', 'N/A')}\n"
            f"  Processed: {maps.computation_info.get('processed_pixels', 'N/A')} px\n"
            f"  dt: {maps.computation_info.get('dt', 'N/A'):.2f} s"
        )
        ax.text(0.1, 0.5, info_text, transform=ax.transAxes,
               fontsize=11, fontfamily='monospace')
        ax.set_title('Info')

    for ax_row in axes:
        for ax in ax_row:
            ax.tick_params(labelsize=8)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Parametric map image saved: {save_path}")

    return fig
