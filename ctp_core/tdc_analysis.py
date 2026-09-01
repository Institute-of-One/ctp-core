"""
Time-density curve (TDC) analysis
========================================
Computes a TDC per region of interest, writes it to CSV and plots it.

For each time point of the TDC it keeps:
- mean CT number (HU)
- standard deviation
- minimum and maximum
- pixel count

The CSV output saves every ROI, every time point and every statistic in one file.

Usage:
    from tdc_analysis import TDCAnalyzer
    analyzer = TDCAnalyzer(volume_4d, metadata)
    tdc_data = analyzer.compute_tdc(roi)
    analyzer.export_csv([tdc_data], "output.csv")
"""

import numpy as np
import csv
import os
from datetime import datetime


class TDCData:
    """Holds the TDC data of a single region of interest.

    To keep the processing from becoming a black box, these are kept as separate
    fields:
        mean           : the raw mean CT number, averaged over the pixels in the ROI
        smoothed       : the curve smoothed along time; identical to mean when no
                         preprocessing was applied
        baseline_value : the estimated baseline, a single scalar
        enhancement    : smoothed - baseline_value
        gamma_fit      : GammaFitResult or None
    """

    def __init__(self, roi_label, time_seconds):
        self.roi_label = roi_label
        self.time_seconds = np.array(time_seconds, dtype=np.float64)
        self.n_times = len(time_seconds)

        # Per-time-point statistics of the raw data
        self.mean = np.zeros(self.n_times, dtype=np.float64)
        self.std = np.zeros(self.n_times, dtype=np.float64)
        self.min_val = np.zeros(self.n_times, dtype=np.float64)
        self.max_val = np.zeros(self.n_times, dtype=np.float64)
        self.pixel_count = np.zeros(self.n_times, dtype=np.int32)

        # Preprocessing results
        self.smoothed = None           # np.ndarray or None
        self.baseline_value = None     # float or None
        self.enhancement = None        # np.ndarray (smoothed - baseline) or raw-baseline
        self.preprocess_description = "(none)"  # a string for the log

        # The gamma fit result: a GammaFitResult, or None
        self.gamma_fit = None

    @property
    def peak_enhancement(self):
        """Return the maximum enhancement."""
        if self.enhancement is not None:
            return float(np.nanmax(self.enhancement))
        return None

    @property
    def time_to_peak(self):
        """Return the time to peak, in seconds."""
        if self.enhancement is not None:
            peak_idx = np.nanargmax(self.enhancement)
            return float(self.time_seconds[peak_idx])
        return None

    @property
    def baseline_mean(self):
        """Return the baseline. Uses baseline_value once preprocessing has run."""
        if self.baseline_value is not None:
            return float(self.baseline_value)
        # Fallback: the mean of the first two time points
        n_baseline = min(2, self.n_times)
        return float(np.mean(self.mean[:n_baseline]))


class TDCAnalyzer:
    """The TDC analysis engine."""

    def __init__(self, volume_4d, metadata):
        """
        Args:
            volume_4d: np.ndarray shape=(n_times, n_slices, rows, cols)
            metadata: dict from dicom_loader
        """
        self.volume = volume_4d
        self.meta = metadata
        self.n_times = metadata['n_times']

    def compute_tdc(self, roi, slice_index=None, preprocess_config=None):
        """Compute the TDC of a given region of interest.

        Args:
            roi: the ROI object (viewer.ROI)
            slice_index: index of the slice; None averages over every slice.
            preprocess_config: a preprocessing.PreprocessConfig, or None.
                               None keeps the older behaviour, in which the mean of
                               the first two time points is the baseline.

        Returns:
            TDCData: the result, holding raw, smoothed, baseline and enhancement
        """
        rows = self.meta['rows']
        cols = self.meta['cols']
        mask = roi.get_mask(rows, cols)

        if mask.sum() == 0:
            raise ValueError(f"There are no pixels inside ROI '{roi.label}'")

        tdc = TDCData(roi.label, self.meta['time_seconds'])

        for t in range(self.n_times):
            if slice_index is not None:
                image = self.volume[t, slice_index, :, :]
            else:
                image = np.mean(self.volume[t, :, :, :], axis=0)

            masked_values = image[mask]
            tdc.mean[t] = np.mean(masked_values)
            tdc.std[t] = np.std(masked_values)
            tdc.min_val[t] = np.min(masked_values)
            tdc.max_val[t] = np.max(masked_values)
            tdc.pixel_count[t] = len(masked_values)

        self._apply_preprocess_to_tdc(tdc, preprocess_config)
        return tdc

    @staticmethod
    def _apply_preprocess_to_tdc(tdc, preprocess_config):
        """Apply preprocessing to TDCData.mean and update tdc.smoothed,
        tdc.baseline_value, tdc.enhancement and tdc.preprocess_description.
        """
        if preprocess_config is None:
            # Older behaviour: the mean of the first two time points is the baseline
            n_baseline = min(2, tdc.n_times)
            baseline = float(np.mean(tdc.mean[:n_baseline]))
            tdc.smoothed = tdc.mean.copy()
            tdc.baseline_value = baseline
            tdc.enhancement = tdc.mean - baseline
            tdc.preprocess_description = "(legacy) baseline=first-2-mean / smooth=none"
            return

        from preprocessing import preprocess_curve
        result = preprocess_curve(tdc.mean, preprocess_config)
        tdc.smoothed = result['smoothed']
        tdc.baseline_value = result['baseline']
        tdc.enhancement = result['corrected']
        tdc.preprocess_description = result['config_description']

    def compute_tdc_from_mask(self, mask, label="ROI", slice_index=None):
        """Compute a TDC directly from a mask array.

        Args:
            mask: np.ndarray shape=(rows, cols), dtype=bool
            label: the label of the region
            slice_index: index of the slice to use

        Returns:
            TDCData
        """
        if mask.sum() == 0:
            raise ValueError(f"There are no pixels inside mask '{label}'")

        tdc = TDCData(label, self.meta['time_seconds'])

        for t in range(self.n_times):
            if slice_index is not None:
                image = self.volume[t, slice_index, :, :]
            else:
                image = np.mean(self.volume[t, :, :, :], axis=0)

            masked_values = image[mask]
            tdc.mean[t] = np.mean(masked_values)
            tdc.std[t] = np.std(masked_values)
            tdc.min_val[t] = np.min(masked_values)
            tdc.max_val[t] = np.max(masked_values)
            tdc.pixel_count[t] = len(masked_values)

        baseline = tdc.baseline_mean
        tdc.enhancement = tdc.mean - baseline

        return tdc

    def compute_pixel_tdc(self, row, col, slice_index):
        """Compute the TDC of a single pixel.

        Args:
            row, col: the pixel coordinates
            slice_index: index of the slice

        Returns:
            TDCData
        """
        tdc = TDCData(f"Pixel({row},{col})", self.meta['time_seconds'])

        for t in range(self.n_times):
            val = float(self.volume[t, slice_index, row, col])
            tdc.mean[t] = val
            tdc.std[t] = 0.0
            tdc.min_val[t] = val
            tdc.max_val[t] = val
            tdc.pixel_count[t] = 1

        baseline = tdc.baseline_mean
        tdc.enhancement = tdc.mean - baseline

        return tdc

    @staticmethod
    def export_csv(tdc_list, filepath,
                   include_raw=True,
                   include_smoothed=False,
                   include_enhancement=True,
                   include_fitted=False,
                   include_stats=True,
                   include_gamma_params=False,
                   aif_curve=None,
                   aif_time_seconds=None,
                   preprocess_description=None,
                   delimiter=','):
        """Write TDC data to a CSV file.

        Args:
            tdc_list: list[TDCData] - the TDC data to write
            filepath: where to write the file
            include_raw:         include the raw mean CT number column
            include_smoothed:    include the smoothed curve column
            include_enhancement: include the baseline-corrected enhancement column
            include_fitted:      include the gamma-variate fit column, for fitted ROIs
            include_stats:       include SD, Min, Max and Pixels, from the raw data
            include_gamma_params: include the fit parameters in the summary
            aif_curve:           optional np.ndarray; adds the AIF curve as a column
            aif_time_seconds:    the AIF time axis; defaults to that of tdc_list[0]
            preprocess_description: the preprocessing settings, recorded at the top
                                 of the summary
            delimiter: the field separator
        """
        if not tdc_list and aif_curve is None:
            raise ValueError("There is no data to save.")

        # The time axis comes from tdc_list[0], or from the AIF
        if tdc_list:
            time_sec = tdc_list[0].time_seconds
            n_times = tdc_list[0].n_times
        else:
            time_sec = np.asarray(aif_time_seconds, dtype=np.float64)
            n_times = len(time_sec)

        # Refuse to write a file with no columns at all
        any_col = any([include_raw, include_smoothed, include_enhancement,
                       include_fitted, aif_curve is not None])
        if not any_col:
            raise ValueError("No columns were selected for output.")

        # Build the header
        header = ['Time(s)']
        for tdc in tdc_list:
            label = tdc.roi_label
            if include_raw:
                header.append(f'{label}_Mean(HU)')
            if include_smoothed and tdc.smoothed is not None:
                header.append(f'{label}_Smoothed(HU)')
            if include_enhancement and tdc.enhancement is not None:
                header.append(f'{label}_Enhancement(HU)')
            if include_fitted and tdc.gamma_fit is not None \
                    and tdc.gamma_fit.success \
                    and tdc.gamma_fit.fitted_curve is not None:
                header.append(f'{label}_Fitted(HU)')
            if include_stats:
                header.append(f'{label}_SD(HU)')
                header.append(f'{label}_Min(HU)')
                header.append(f'{label}_Max(HU)')
                header.append(f'{label}_Pixels')
        if aif_curve is not None:
            header.append('AIF_Curve(HU)')
            if include_enhancement:
                header.append('AIF_Enhancement(HU)')

        # Data rows
        data_rows = []
        aif_arr = np.asarray(aif_curve, dtype=np.float64) if aif_curve is not None else None
        aif_baseline = (
            float(np.mean(aif_arr[:min(2, len(aif_arr))]))
            if aif_arr is not None else None
        )

        for t in range(n_times):
            row = [f'{time_sec[t]:.3f}']
            for tdc in tdc_list:
                if include_raw:
                    row.append(f'{tdc.mean[t]:.2f}')
                if include_smoothed and tdc.smoothed is not None:
                    row.append(f'{tdc.smoothed[t]:.2f}')
                if include_enhancement and tdc.enhancement is not None:
                    row.append(f'{tdc.enhancement[t]:.2f}')
                if include_fitted and tdc.gamma_fit is not None \
                        and tdc.gamma_fit.success \
                        and tdc.gamma_fit.fitted_curve is not None:
                    # Add the baseline back, so the fit is on the original scale
                    val = tdc.gamma_fit.fitted_curve[t] + float(tdc.baseline_value or 0.0)
                    row.append(f'{val:.2f}')
                if include_stats:
                    row.append(f'{tdc.std[t]:.2f}')
                    row.append(f'{tdc.min_val[t]:.2f}')
                    row.append(f'{tdc.max_val[t]:.2f}')
                    row.append(f'{tdc.pixel_count[t]}')
            if aif_arr is not None and t < len(aif_arr):
                row.append(f'{aif_arr[t]:.2f}')
                if include_enhancement:
                    row.append(f'{aif_arr[t] - aif_baseline:.2f}')
            data_rows.append(row)

        # Summary
        summary_rows = [[], ['# Summary']]
        if preprocess_description:
            summary_rows.append([f'# preprocess: {preprocess_description}'])
        for tdc in tdc_list:
            line = [
                f'# {tdc.roi_label}',
                f'Baseline={tdc.baseline_mean:.2f} HU',
                f'PeakEnhancement={tdc.peak_enhancement:.2f} HU',
                f'TimeToPeak={tdc.time_to_peak:.2f} s',
                f'Pixels={tdc.pixel_count[0]}',
            ]
            if include_gamma_params and tdc.gamma_fit is not None:
                gf = tdc.gamma_fit
                if gf.success:
                    line.append(
                        f'Gamma: K={gf.K:.3e} t0={gf.t0:.2f} '
                        f'alpha={gf.alpha:.3f} beta={gf.beta:.3f} '
                        f'R2={gf.r_squared:.4f} BAT={gf.bat:.2f}s '
                        f'TTP_fit={gf.peak_time:.2f}s '
                        f'Peak_fit={gf.peak_value:.2f}HU '
                        f'AUC_fit={gf.auc:.2f}'
                    )
                else:
                    line.append(f'Gamma: FAIL ({gf.error_message})')
            summary_rows.append(line)
        if aif_arr is not None:
            summary_rows.append([
                f'# AIF',
                f'Baseline={aif_baseline:.2f} HU',
                f'Peak={float(np.max(aif_arr)):.2f} HU',
                f'TTP={float(time_sec[int(np.argmax(aif_arr))]):.2f} s',
                f'Samples={len(aif_arr)}',
            ])

        # Write the file as UTF-8 with a BOM, for compatibility with Excel
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerow(header)
            writer.writerows(data_rows)
            writer.writerows(summary_rows)

        print(f"TDC data saved: {filepath}")
        print(f"  ROIs: {len(tdc_list)}, time points: {n_times}, columns: {len(header)}")

    @staticmethod
    def export_all_pixel_tdc_csv(volume_4d, metadata, slice_index,
                                  filepath, mask=None):
        """Write the TDC of every pixel of a slice, or of every pixel inside a mask,
        to a single CSV file.

        This is something ordinary perfusion software does not offer.

        Args:
            volume_4d: the 4D volume
            metadata: the metadata
            slice_index: index of the slice to use
            filepath: where to write the file
            mask: a pixel filter; None means every pixel

        Output format:
            Row, Col, T0(HU), T1(HU), T2(HU), ..., Enhancement_Peak, Time_to_Peak
        """
        n_times = metadata['n_times']
        rows = metadata['rows']
        cols = metadata['cols']
        time_seconds = metadata['time_seconds']

        # Header
        header = ['Row', 'Col']
        for t in range(n_times):
            header.append(f'T{t}_{time_seconds[t]:.1f}s(HU)')
        header.extend(['Baseline(HU)', 'PeakEnhancement(HU)', 'TimeToPeak(s)'])

        data_rows = []
        slice_data = volume_4d[:, slice_index, :, :]  # shape: (n_times, rows, cols)

        for r in range(rows):
            for c in range(cols):
                if mask is not None and not mask[r, c]:
                    continue

                values = slice_data[:, r, c]
                baseline = float(np.mean(values[:2]))
                enhancement = values - baseline
                peak_enh = float(np.max(enhancement))
                ttp_idx = int(np.argmax(enhancement))
                ttp = time_seconds[ttp_idx]

                row = [r, c]
                row.extend([f'{v:.1f}' for v in values])
                row.extend([f'{baseline:.1f}', f'{peak_enh:.1f}', f'{ttp:.1f}'])
                data_rows.append(row)

        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(data_rows)

        print(f"All-pixel TDC saved: {filepath}")
        print(f"  pixels: {len(data_rows)}, time points: {n_times}")


def plot_tdc(tdc_list, title="Time-Density Curve", show_enhancement=False,
             save_path=None):
    """Plot TDC curves.

    Args:
        tdc_list: list[TDCData]
        title: the plot title
        show_enhancement: when True, show the difference from baseline
        save_path: where to save the image; None only displays it
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))

    for tdc in tdc_list:
        t = tdc.time_seconds
        if show_enhancement:
            y = tdc.enhancement
            ylabel = 'Enhancement (HU)'
        else:
            y = tdc.mean
            ylabel = 'CT Value (HU)'

        ax.plot(t, y, 'o-', label=tdc.roi_label, linewidth=2, markersize=4)

        # Error bars, +/- 1 SD
        ax.fill_between(
            t, y - tdc.std, y + tdc.std,
            alpha=0.15
        )

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    # Summary information
    summary_lines = []
    for tdc in tdc_list:
        summary_lines.append(
            f"{tdc.roi_label}: Peak={tdc.peak_enhancement:.1f}HU, "
            f"TTP={tdc.time_to_peak:.1f}s, "
            f"Baseline={tdc.baseline_mean:.1f}HU"
        )
    ax.text(
        0.02, 0.02, "\n".join(summary_lines),
        transform=ax.transAxes, fontsize=8,
        verticalalignment='bottom',
        bbox=dict(boxstyle='round', facecolor='white', alpha=0.8)
    )

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"TDC plot saved: {save_path}")

    return fig, ax
