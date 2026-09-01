"""
Automatic detection of the arterial input function (AIF)
=================================================
Detects the arterial input function automatically from CT-perfusion data.

How the algorithm works:
-------
Following Rempp et al. (1994) and Mouridsen et al. (2006), voxels with the
properties below are taken as arterial candidates:

1. a high peak enhancement (in the top few per cent)
2. an early arrival (a short time to peak)
3. a steep upslope (a large wash-in slope)
4. a narrow curve (a small full width at half maximum)

References:
- Rempp KA, et al. "Quantification of regional cerebral blood flow
  and volume with dynamic susceptibility contrast-enhanced MR imaging."
  Radiology. 1994;193(3):637-641.
  -> on modelling the first pass of the contrast agent:
    "The arterial input function C_a(t) was measured in pixels
     within the middle cerebral artery..."

- Mouridsen K, et al. "Automatic selection of arterial input function
  using cluster analysis." Magnetic Resonance in Medicine. 2006;55(3):524-531.
  -> on using clustering to select the AIF automatically:
    "Voxels were initially screened using the following criteria:
     (1) peak concentration above a threshold,
     (2) time to peak (TTP) earlier than the mean,
     (3) first moment of the concentration-time curve below the mean."
  -> the AIF is characterised by "early arrival, high peak, narrow width"

- Fieselmann A, et al. "Automatic determination of the arterial input
  function in dynamic CT." Medical Physics. 2011;38(4):2468-2480.
  -> automatic AIF detection specific to CT perfusion: threshold-based screening
    followed by ranking the candidates on shape features:
    "Candidate voxels were selected based on (1) peak enhancement
     > T_peak, (2) TTP within a temporal window, and (3) FWHM
     below a threshold."

Usage:
    from aif_detection import AIFDetector
    detector = AIFDetector(volume_4d, metadata)
    aif_result = detector.detect(slice_index=2)
    print(aif_result.aif_curve)
"""

import numpy as np
from scipy import ndimage
from scipy.signal import find_peaks


class AIFResult:
    """Holds the result of AIF detection."""

    def __init__(self):
        self.aif_curve = None          # the mean AIF curve (n_times,)
        self.aif_enhancement = None    # the enhancement curve (n_times,)
        self.aif_mask = None           # mask of the AIF voxels (rows, cols)
        self.candidate_mask = None     # mask of the candidate voxels
        self.n_aif_voxels = 0
        self.aif_center = None         # centroid of the AIF cluster (row, col)
        self.time_seconds = None
        self.detection_info = {}       # the detection parameters


class AIFDetector:
    """The automatic AIF detection engine.

    The detection algorithm, implemented for CT following Fieselmann et al. 2011:

    Phase 1: screen the candidate voxels
        - peak enhancement at or above a threshold
        - TTP at or below the median over all voxels, so arrival is early
        - baseline CT number inside a range, excluding bone and air

    Phase 2: rank on shape features
        - a small FWHM
        - a large wash-in slope
        - a high peak enhancement

    Phase 3: clustering
        - cluster the spatially close voxels among the top candidates
        - take the mean of the largest cluster as the AIF
    """

    def __init__(self, volume_4d, metadata):
        self.volume = volume_4d
        self.meta = metadata
        self.n_times = metadata['n_times']
        self.rows = metadata['rows']
        self.cols = metadata['cols']
        self.time_seconds = np.array(metadata['time_seconds'])

    def _compute_enhancement_map(self, slice_data, n_baseline=2):
        """Compute the enhancement map.

        Args:
            slice_data: shape=(n_times, rows, cols)
            n_baseline: number of time points used as the baseline

        Returns:
            enhancement: shape=(n_times, rows, cols)
            baseline: shape=(rows, cols)
        """
        baseline = np.mean(slice_data[:n_baseline], axis=0)
        enhancement = slice_data - baseline[np.newaxis, :, :]
        return enhancement, baseline

    def _compute_peak_map(self, enhancement):
        """Compute the peak-enhancement map and the TTP map.

        Returns:
            peak_map: shape (rows, cols), the maximum enhancement
            ttp_map: shape (rows, cols), the index of the peak
        """
        peak_map = np.max(enhancement, axis=0)
        ttp_map = np.argmax(enhancement, axis=0)
        return peak_map, ttp_map

    def _compute_fwhm_map(self, enhancement):
        """Compute the FWHM of each pixel, in frames.

        Returns:
            fwhm_map: shape (rows, cols), the half width in time points
        """
        peak_vals = np.max(enhancement, axis=0)
        half_max = peak_vals / 2.0

        fwhm_map = np.full((self.rows, self.cols), self.n_times, dtype=np.float32)

        for r in range(self.rows):
            for c in range(self.cols):
                if peak_vals[r, c] <= 0:
                    continue
                curve = enhancement[:, r, c]
                above_half = curve >= half_max[r, c]
                if np.any(above_half):
                    indices = np.where(above_half)[0]
                    fwhm_map[r, c] = indices[-1] - indices[0] + 1

        return fwhm_map

    def _compute_fwhm_map_fast(self, enhancement):
        """A fast, vectorized version of the FWHM."""
        peak_vals = np.max(enhancement, axis=0)  # (rows, cols)
        half_max = peak_vals / 2.0  # (rows, cols)

        # Whether each time point is at or above half maximum
        above_half = enhancement >= half_max[np.newaxis, :, :]  # (n_times, rows, cols)

        # Find the first and last True index
        # using a cumulative sum along the time axis.
        first_above = np.argmax(above_half, axis=0).astype(np.float32)
        last_above = (self.n_times - 1 - np.argmax(above_half[::-1], axis=0)).astype(np.float32)

        fwhm_map = last_above - first_above + 1
        fwhm_map[peak_vals <= 0] = self.n_times

        return fwhm_map

    def _compute_washin_slope(self, enhancement, ttp_map):
        """Compute the wash-in slope map.

        The maximum slope from the baseline to the peak.

        Returns:
            slope_map: shape=(rows, cols)
        """
        dt = np.diff(self.time_seconds)
        if np.all(dt == 0):
            dt = np.ones(self.n_times - 1)

        slope_map = np.zeros((self.rows, self.cols), dtype=np.float32)

        # Time derivative
        d_enhancement = np.diff(enhancement, axis=0)  # (n_times-1, rows, cols)
        for i in range(len(dt)):
            d_enhancement[i] /= max(dt[i], 0.001)

        # The maximum slope up to the peak
        slope_map = np.max(d_enhancement, axis=0)

        return slope_map

    def detect(self, slice_index=None, n_baseline=2,
               peak_percentile=95, ttp_percentile=40,
               baseline_min=-50, baseline_max=80,
               peak_ct_max=500, skull_erosion_px=5,
               n_top_candidates=200, min_cluster_size=3):
        """Run the automatic AIF detection.

        Args:
            slice_index: the slice to use; None detects across every slice
            n_baseline: number of baseline time points
            peak_percentile: percentile threshold on the peak enhancement
            ttp_percentile: percentile threshold on TTP; at or below it is a candidate
            baseline_min/max: allowed range of the baseline CT number (HU).
                              Brain parenchyma is 20-45 HU; above 80 HU is likely bone.
            peak_ct_max: upper bound on the absolute CT number at peak (HU).
                         Bone stays near 1000 HU after contrast; arteries reach 300-500.
            skull_erosion_px: distance excluded around high-CT (bone) regions, in pixels
            n_top_candidates: how many top-scoring candidates to keep
            min_cluster_size: the minimum cluster size

        Returns:
            AIFResult
        """
        result = AIFResult()
        result.time_seconds = self.time_seconds

        # Data for the slice being processed
        if slice_index is not None:
            slice_data = self.volume[:, slice_index, :, :]
        else:
            slice_data = np.mean(self.volume, axis=1)

        # Phase 1: compute the basic features
        print("AIF detection, phase 1: computing features...")
        enhancement, baseline = self._compute_enhancement_map(slice_data, n_baseline)
        peak_map, ttp_map = self._compute_peak_map(enhancement)

        # Phase 1: screening, relaxed in stages
        print("AIF detection, phase 1: screening the candidate voxels...")

        # Build the bone mask, used at every stage
        peak_ct_map = np.max(slice_data, axis=0)
        bone_mask = baseline > 150

        # The threshold sets, relaxed in stages
        # (baseline_max, peak_ct_max, skull_erosion_px, peak_pctl, ttp_pctl)
        relaxation_levels = [
            (baseline_max, peak_ct_max, skull_erosion_px,
             peak_percentile, ttp_percentile),
            (120, 600, 3, peak_percentile, ttp_percentile),
            (150, 800, 2, 90, 50),
            (200, 1000, 1, 85, 60),
            (300, 1500, 0, 80, 70),
        ]

        candidate_mask = None
        n_candidates = 0
        used_level = 0

        for level_idx, (bl_max, pct_max, ero_px, p_pctl, t_pctl) in enumerate(relaxation_levels):
            # Condition 1: the peak enhancement is among the highest
            if np.any(peak_map > 0):
                peak_threshold = np.percentile(peak_map[peak_map > 0], p_pctl)
            else:
                break
            mask_peak = peak_map >= peak_threshold

            # Condition 2: TTP is early
            valid_ttp = ttp_map[peak_map > 0]
            ttp_threshold = np.percentile(valid_ttp, t_pctl)
            mask_ttp = ttp_map <= ttp_threshold

            # Condition 3: the baseline CT number is in range
            mask_baseline = (baseline >= baseline_min) & (baseline <= bl_max)

            # Condition 4: the absolute CT number at peak
            mask_peak_ct = peak_ct_map < pct_max

            # Condition 5: exclude anything near bone
            if np.any(bone_mask) and ero_px > 0:
                bone_dilated = ndimage.binary_dilation(
                    bone_mask, iterations=ero_px)
                mask_not_near_bone = ~bone_dilated
            else:
                mask_not_near_bone = np.ones_like(baseline, dtype=bool)

            candidate_mask = (mask_peak & mask_ttp & mask_baseline &
                              mask_peak_ct & mask_not_near_bone)
            n_candidates = int(candidate_mask.sum())
            used_level = level_idx

            if n_candidates >= min_cluster_size:
                if level_idx > 0:
                    print(f"  thresholds relaxed to stage {level_idx} "
                          f"(baseline_max={bl_max}, peak_ct_max={pct_max}, "
                          f"erosion={ero_px}px)")
                break

        result.candidate_mask = candidate_mask
        print(f"  candidate voxels: {n_candidates}")

        if n_candidates == 0:
            print("  [WARNING] no AIF candidate was found.")
            return result

        # Phase 2: rank on shape features
        # (Fieselmann 2011: "FWHM below a threshold" + ranking by shape)
        print("AIF detection, phase 2: ranking on shape features...")

        fwhm_map = self._compute_fwhm_map_fast(enhancement)
        slope_map = self._compute_washin_slope(enhancement, ttp_map)

        # Score each candidate:
        # score = norm(peak) + norm(slope) - norm(fwhm) - norm(ttp)
        candidate_indices = np.where(candidate_mask)
        n_cand = len(candidate_indices[0])

        peaks = peak_map[candidate_indices]
        ttps = ttp_map[candidate_indices].astype(np.float32)
        fwhms = fwhm_map[candidate_indices]
        slopes = slope_map[candidate_indices]

        def normalize(arr):
            rng = arr.max() - arr.min()
            if rng == 0:
                return np.zeros_like(arr)
            return (arr - arr.min()) / rng

        score = (normalize(peaks) +
                 normalize(slopes) -
                 normalize(fwhms) -
                 normalize(ttps))

        # Select the top candidates
        n_top = min(n_top_candidates, n_cand)
        top_indices = np.argsort(score)[::-1][:n_top]

        top_mask = np.zeros_like(candidate_mask)
        top_rows = candidate_indices[0][top_indices]
        top_cols = candidate_indices[1][top_indices]
        top_mask[top_rows, top_cols] = True

        # Phase 3: spatial clustering
        # (Mouridsen 2006: cluster analysis approach)
        print("AIF detection, phase 3: spatial clustering...")

        labeled, n_clusters = ndimage.label(top_mask)
        if n_clusters == 0:
            print("  [WARNING] no cluster was formed.")
            return result

        # Select the largest cluster
        cluster_sizes = ndimage.sum(top_mask, labeled, range(1, n_clusters + 1))
        best_cluster = np.argmax(cluster_sizes) + 1
        best_size = int(cluster_sizes[best_cluster - 1])

        if best_size < min_cluster_size:
            # When the cluster is too small, use the top-scoring voxels directly.
            print(f"  the largest cluster is small ({best_size} voxels); "
                  f"using the top {min_cluster_size} voxels instead.")
            aif_mask = np.zeros_like(candidate_mask)
            for i in range(min(min_cluster_size, n_top)):
                aif_mask[top_rows[i], top_cols[i]] = True
        else:
            aif_mask = (labeled == best_cluster)
            print(f"  largest cluster: {best_size} voxels")

        result.aif_mask = aif_mask
        result.n_aif_voxels = int(aif_mask.sum())

        # Centroid of the AIF cluster
        aif_indices = np.where(aif_mask)
        result.aif_center = (
            float(np.mean(aif_indices[0])),
            float(np.mean(aif_indices[1]))
        )

        # Compute the AIF curve, the mean over the voxels in the mask
        aif_curve = np.zeros(self.n_times)
        for t in range(self.n_times):
            aif_curve[t] = np.mean(slice_data[t][aif_mask])

        result.aif_curve = aif_curve
        aif_baseline = np.mean(aif_curve[:n_baseline])
        result.aif_enhancement = aif_curve - aif_baseline

        # Store the detection information
        result.detection_info = {
            'slice_index': slice_index,
            'n_baseline': n_baseline,
            'peak_percentile': peak_percentile,
            'peak_threshold': float(peak_threshold),
            'ttp_percentile': ttp_percentile,
            'ttp_threshold': float(ttp_threshold),
            'n_initial_candidates': n_candidates,
            'n_top_candidates': n_top,
            'n_clusters': n_clusters,
            'best_cluster_size': best_size,
            'aif_center': result.aif_center,
            'aif_peak_enhancement': float(np.max(result.aif_enhancement)),
            'aif_ttp': float(self.time_seconds[np.argmax(result.aif_enhancement)]),
        }

        print(f"\nAIF detection complete:")
        print(f"  AIF voxels: {result.n_aif_voxels}")
        print(f"  AIF centre: ({result.aif_center[0]:.1f}, {result.aif_center[1]:.1f})")
        print(f"  peak enhancement: {result.detection_info['aif_peak_enhancement']:.1f} HU")
        print(f"  Time to Peak: {result.detection_info['aif_ttp']:.1f} s")

        return result

    def extract_aif_at(self, row, col, slice_index=None,
                       radius=3, n_baseline=2):
        """Extract an AIF manually from a small disc around a given point (row, col).

        For use when automatic detection fails, or when the user wants to name an
        arterial location: the AIF is the mean of the voxels within ``radius`` of the
        clicked point. The return value has the same structure as automatic detection
        (``detect``), an AIFResult, so the existing display, fitting and output paths
        can be used unchanged.

        Args:
            row, col: image coordinates (row, column); floats are accepted and rounded.
            slice_index: the slice to use; None averages over every slice.
            radius: radius of the disc to average, in pixels.
            n_baseline: number of baseline time points.

        Returns:
            AIFResult (aif_curve, aif_enhancement, aif_mask, aif_center and so on)
        """
        result = AIFResult()
        result.time_seconds = self.time_seconds

        if slice_index is not None:
            slice_data = self.volume[:, slice_index, :, :]
        else:
            slice_data = np.mean(self.volume, axis=1)

        rr = int(np.clip(round(row), 0, self.rows - 1))
        cc = int(np.clip(round(col), 0, self.cols - 1))
        r = max(int(radius), 0)

        yy, xx = np.ogrid[:self.rows, :self.cols]
        mask = (yy - rr) ** 2 + (xx - cc) ** 2 <= r ** 2
        if not np.any(mask):
            mask[rr, cc] = True

        result.aif_mask = mask
        result.candidate_mask = mask
        result.n_aif_voxels = int(np.count_nonzero(mask))
        result.aif_center = (float(rr), float(cc))

        aif_curve = np.array(
            [float(np.mean(slice_data[t][mask])) for t in range(self.n_times)]
        )
        result.aif_curve = aif_curve
        aif_baseline = float(np.mean(aif_curve[:n_baseline]))
        result.aif_enhancement = aif_curve - aif_baseline

        result.detection_info = {
            'manual': True,
            'slice_index': slice_index,
            'point': (rr, cc),
            'radius': r,
            'n_baseline': n_baseline,
            'aif_center': result.aif_center,
            'aif_peak_enhancement': float(np.max(result.aif_enhancement)),
            'aif_ttp': float(self.time_seconds[np.argmax(result.aif_enhancement)]),
        }
        print(f"[manual AIF] centre=({rr},{cc}) radius={r}px "
              f"voxels={result.n_aif_voxels} "
              f"peak enhancement={result.detection_info['aif_peak_enhancement']:.1f}HU")
        return result


def plot_aif_detection(volume_4d, metadata, aif_result, slice_index,
                       save_path=None):
    """Display the AIF detection result.

    Four panels:
    1. top left: the original image with the AIF location
    2. top right: the peak-enhancement map with the candidate voxels
    3. bottom left: the AIF curve
    4. bottom right: the TTP map with the AIF cluster
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("AIF Auto-Detection Result", fontsize=14, fontweight='bold')

    # The baseline image
    baseline_img = np.mean(volume_4d[:2, slice_index, :, :], axis=0)

    # --- top left: the original image with the AIF location ---
    ax = axes[0, 0]
    ax.imshow(baseline_img, cmap='gray', vmin=0, vmax=100)
    if aif_result.aif_mask is not None:
        # Overlay the AIF mask in red
        overlay = np.zeros((*aif_result.aif_mask.shape, 4))
        overlay[aif_result.aif_mask, 0] = 1.0
        overlay[aif_result.aif_mask, 3] = 0.5
        ax.imshow(overlay)

        if aif_result.aif_center:
            ax.plot(aif_result.aif_center[1], aif_result.aif_center[0],
                   'r+', markersize=15, markeredgewidth=2)

    ax.set_title("Baseline Image + AIF Location")

    # --- top right: the peak-enhancement map ---
    ax = axes[0, 1]
    enhancement = volume_4d[:, slice_index, :, :] - baseline_img[np.newaxis, :, :]
    peak_map = np.max(enhancement, axis=0)
    im = ax.imshow(peak_map, cmap='hot', vmin=0,
                   vmax=np.percentile(peak_map[peak_map > 0], 99))
    plt.colorbar(im, ax=ax, label='Peak Enhancement (HU)')

    if aif_result.candidate_mask is not None:
        # The candidate voxels as green dots
        cand_idx = np.where(aif_result.candidate_mask)
        ax.plot(cand_idx[1], cand_idx[0], 'g.', markersize=1, alpha=0.5)

    ax.set_title("Peak Enhancement Map + Candidates")

    # --- bottom left: the AIF curve ---
    ax = axes[1, 0]
    if aif_result.aif_curve is not None:
        ax.plot(aif_result.time_seconds, aif_result.aif_curve,
               'r-o', linewidth=2, markersize=4, label='AIF')
        ax.plot(aif_result.time_seconds, aif_result.aif_enhancement,
               'b--', linewidth=1, alpha=0.7, label='Enhancement')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('CT Value (HU)')
        ax.legend()
        ax.grid(True, alpha=0.3)
    ax.set_title("Detected AIF Curve")

    # --- bottom right: the TTP map ---
    ax = axes[1, 1]
    ttp_map = np.argmax(enhancement, axis=0).astype(np.float32)
    ttp_map[peak_map <= 10] = np.nan  # mask the regions with no enhancement
    im = ax.imshow(ttp_map, cmap='jet')
    plt.colorbar(im, ax=ax, label='Time to Peak (phase)')

    if aif_result.aif_mask is not None:
        aif_idx = np.where(aif_result.aif_mask)
        ax.plot(aif_idx[1], aif_idx[0], 'w+', markersize=3)

    ax.set_title("TTP Map + AIF Cluster")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"AIF detection result saved: {save_path}")

    return fig
