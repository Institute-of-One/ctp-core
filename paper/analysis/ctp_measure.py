"""The measurement logic behind the manuscript, as functions that can be tested.

The decisions the paper rests on are implemented here, as functions a test can call: the
validity rule, the quantisation floor, the positive-area integral, the CBV ratio and the
hemispheric split.

**The drivers are not free of arithmetic, and an earlier version of this docstring claimed they
were.** A reviewer corrected it. ``run_aif`` forms the area ratio and its median and range,
``run_reference`` forms each stratum's bias, standard deviation and RMSE, and ``run_clinical``
forms the hemispheric means, medians and their difference. Those are ordinary aggregations over
the values these functions return, and they are summarised rather than individually tested; what
this module's tests cover is the part where a wrong answer would not look wrong.

Three of these encode decisions that were made after looking at data and are recorded as
amendments in ``paper/PROTOCOL.md``:

* :func:`fitted_peak_time` applies the **validity rule** — a fitted peak outside the times that
  were actually sampled is not a measurement. ``fit_gamma_variate`` reports success for such
  fits, so without this rule they reach the mean: on one case they produced a hemispheric
  difference of +17.9 s where the admitted fits give +0.24 s.
* :func:`sampled_peak_time` is the fit-free path, whose output can only lie on the sampling
  grid. Its precision floor is :func:`quantisation_floor`.
* :func:`hemispheres` splits at the column centroid of the mask rather than the image centre,
  because the head is not always centred in the field of view.

Domain. These functions take enhancement values in Hounsfield units and times in seconds:
magnitudes of order 1 to 10^4, and sample counts of order 10 to 10^2. Reviews raised failures
that need inputs near the floating-point limits — an argmax that shifts because integers beyond
2^53 are not exactly representable as doubles, a trapezoid that overflows at 10^308. Those are
real for arbitrary doubles and unreachable for this data, so the domain is stated here rather
than defended with machinery that the measurement would never exercise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: The physiological range these measurements live in, enforced by :func:`cbv_from_areas`.
#: Real arterial areas on this dataset are 5e3 to 1.2e4 HU.s and brain density is 1.04 g/ml,
#: so these bounds are generous by many orders of magnitude while still excluding the
#: floating-point corner cases that three rounds of review kept finding.
MAX_AREA = 1e12
#: A positive lower bound on the arterial area. Both reviewers found, independently, that
#: bounding only from above still let a vanishingly small positive area through and produce an
#: infinite or silently lost result. With this floor the output is bounded above by
#: MAX_AREA / MIN_AREA / MIN_DENSITY * 100 = 1e21, so no admitted input can overflow.
MIN_AREA = 1e-6
MIN_DENSITY = 0.1
MAX_DENSITY = 10.0

__all__ = [
    "MAX_AREA",
    "MIN_AREA",
    "MIN_DENSITY",
    "MAX_DENSITY",
    "sampled_peak_time",
    "fitted_peak_time",
    "quantisation_floor",
    "curve_area",
    "cbv_from_areas",
    "hemispheres",
    "HemisphereSplit",
    "FitRejection",
]


class FitRejection(str):
    """Why a fit was not admitted. A plain string so it survives JSON unchanged."""

    FAILED = "fit_failed"
    OUTSIDE_WINDOW = "peak_outside_sampled_window"


def sampled_peak_time(times: np.ndarray, curve: np.ndarray) -> float:
    """Time to peak taken as the argmax of the sampled curve.

    The result can only be one of ``times``; that is the whole point of the comparison in the
    manuscript, not an implementation shortcut.
    """
    times = np.asarray(times, dtype=float)
    curve = np.asarray(curve, dtype=float)
    if times.ndim != 1 or curve.shape != times.shape:
        raise ValueError(f"times {times.shape} and curve {curve.shape} must match and be 1-D")
    if times.size == 0:
        raise ValueError("an empty curve has no peak")
    # np.argmax returns the index of the first NaN rather than ignoring it, so a single bad
    # sample would be reported as the peak with no indication that anything was wrong.
    if not np.all(np.isfinite(times)) or not np.all(np.isfinite(curve)):
        raise ValueError("times and curve must be finite")
    return float(times[int(np.argmax(curve))])


def fitted_peak_time(
    peak_time: float | None,
    *,
    success: bool,
    window: tuple[float, float],
) -> tuple[float | None, str | None]:
    """Admit a fitted peak time, or say why it was rejected.

    ``peak_time`` is derived analytically from the fitted parameters, so nothing in the fit
    itself keeps it inside the acquisition. Returns ``(value, None)`` when admitted and
    ``(None, reason)`` when not.
    """
    low, high = float(window[0]), float(window[1])
    if not (math.isfinite(low) and math.isfinite(high)):
        raise ValueError(f"window {window} must be finite")
    if low > high:
        raise ValueError(f"window {window} is reversed")
    if not success or peak_time is None or not math.isfinite(float(peak_time)):
        return None, FitRejection.FAILED
    value = float(peak_time)
    if not (low <= value <= high):
        return None, FitRejection.OUTSIDE_WINDOW
    return value, None


def quantisation_floor(dt: float) -> float:
    """Standard deviation of a value rounded to a grid of spacing ``dt``.

    A uniform distribution over one cell has standard deviation ``dt / sqrt(12)``. This is the
    precision the fit-free path cannot beat however much the noise is reduced, because the
    limit is the sampling grid rather than the noise.
    """
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be a positive finite number")
    return float(dt) / math.sqrt(12.0)


def curve_area(times: np.ndarray, curve: np.ndarray) -> float:
    """Area under the positive part of the piecewise-linear curve through the samples.

    The samples are joined by straight lines and only the part above zero is integrated, so a
    segment that crosses zero contributes the triangle above the crossing and nothing below it.

    The obvious shortcut — clip the samples, then integrate — is wrong wherever the curve
    changes sign between two samples, because clipping moves the crossing to the sample. Both
    reviewers found it independently: ``curve_area([0, 1], [-1, 1])`` returned 0.5 where the
    line crosses zero at t = 0.5 and the correct positive area is 0.25. Measured arterial input
    curves do dip below zero on the baseline, so this is not a hypothetical case.
    """
    times = np.asarray(times, dtype=float)
    curve = np.asarray(curve, dtype=float)
    if times.ndim != 1 or curve.shape != times.shape:
        raise ValueError(f"times {times.shape} and curve {curve.shape} must match and be 1-D")
    if not np.all(np.isfinite(times)) or not np.all(np.isfinite(curve)):
        raise ValueError("times and curve must be finite")
    if times.size < 2:
        return 0.0

    total = 0.0
    for start, end, left, right in zip(times[:-1], times[1:], curve[:-1], curve[1:], strict=True):
        span = float(end - start)
        if span <= 0.0:
            raise ValueError("times must be strictly increasing")
        if left >= 0.0 and right >= 0.0:
            total += 0.5 * (left + right) * span
        elif left <= 0.0 and right <= 0.0:
            continue
        else:
            # One endpoint above zero, one below: integrate the triangle on the positive side.
            crossing = span * left / (left - right)
            if left > 0.0:
                total += 0.5 * float(left) * crossing
            else:
                total += 0.5 * float(right) * (span - crossing)
    return float(total)


def cbv_from_areas(tissue_area: float, aif_area: float, density: float = 1.04) -> float:
    """Cerebral blood volume in ml/100 g, as the ratio of the two areas.

    Written out because the manuscript's central quantitative claim rests on it: an arterial
    area that is too small by a factor k inflates CBV by exactly k, with nothing else involved.
    """
    # The domain is enforced rather than described. Three rounds of review found a different
    # floating-point failure each time -- sequential division overflowing, then the product
    # overflowing and returning a silent zero -- and each fix moved the failure rather than
    # removing it. Being correct for every double would take scaling machinery that this
    # measurement will never exercise: areas here are enhancement integrated over seconds,
    # 10^2 to 10^4 HU.s, and brain density is near 1.04 g/ml. Outside that, the honest answer
    # is to refuse rather than to return a number nobody has checked.
    if not (math.isfinite(tissue_area) and 0.0 <= tissue_area <= MAX_AREA):
        raise ValueError(f"tissue area {tissue_area} outside the supported range "
                         f"0 to {MAX_AREA:g} HU.s")
    if not (math.isfinite(aif_area) and MIN_AREA <= aif_area <= MAX_AREA):
        raise ValueError(f"arterial area {aif_area} outside the supported range "
                         f"[{MIN_AREA:g}, {MAX_AREA:g}] HU.s")
    if not (math.isfinite(density) and MIN_DENSITY <= density <= MAX_DENSITY):
        raise ValueError(f"density {density} outside the supported range "
                         f"[{MIN_DENSITY:g}, {MAX_DENSITY:g}] g/ml")
    # Restore the scale before dividing, not after: with the bounds above, tissue_area * 100
    # cannot overflow, while dividing first can underflow to zero for a tiny tissue area and
    # then be multiplied back up from nothing.
    return float(tissue_area * 100.0 / aif_area / density)


@dataclass(frozen=True)
class HemisphereSplit:
    left: np.ndarray
    right: np.ndarray
    midline: int


def hemispheres(mask: np.ndarray) -> HemisphereSplit:
    """Split a tissue mask at the column centroid of the mask itself.

    The midline is taken from the data rather than from the image centre: the head is not
    always centred, and a fixed centre column would move tissue from one hemisphere to the
    other. The column at the midline belongs to the right side, so the two parts are disjoint
    and together cover the mask.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError(f"expected a 2-D mask, got {mask.shape}")
    if not mask.any():
        raise ValueError("an empty mask has no midline")
    weights = mask.sum(axis=0)
    centroid = float(np.average(np.arange(mask.shape[1]), weights=weights))
    # math.floor(x + 0.5), not round(): Python rounds a half to the even integer, so a mask
    # whose centroid falls exactly between two columns -- which is every left-right symmetric
    # mask of even width -- was split one column off balance for half of all widths, and a
    # test passed only because its width happened to have the lucky parity. A review caught it.
    midline = math.floor(centroid + 0.5)
    left = mask.copy()
    left[:, midline:] = False
    right = mask.copy()
    right[:, :midline] = False
    return HemisphereSplit(left=left, right=right, midline=midline)
