r"""Reading the UniToBrain test set, for the clinical arm of the manuscript.

The dataset is public, de-identified and openly licensed, and it is not redistributed here.
Set ``UNITOBRAIN_ROOT`` to the directory holding the extracted ``test`` folder:

    set UNITOBRAIN_ROOT=...\UniToBrain\test_set\test        (cmd)
    $env:UNITOBRAIN_ROOT = "...\UniToBrain\test_set\test"   (PowerShell)
    export UNITOBRAIN_ROOT=.../UniToBrain/test_set/test     (sh)

There is deliberately no default. A default is one machine's directory layout, and a reader
who has the dataset somewhere else is better served by an error naming the variable than by a
path that does not exist on their computer.

What the set contains, and the two things about it that matter for the measurement:

* Each case ships three series -- the raw acquisition, a registered version, and the registered
  version filtered at 3 mm / 20 HU -- plus reference perfusion maps (``NLR_CBF``, ``NLR_CBV``,
  ``NLR_MTT``, ``NLR_TTP``, ``NLR_Delay``) produced from the filtered series. Those maps are the
  independent reference the manuscript compares against.
* Beside the maps is a two-line text file holding **the time vector and the arterial input curve
  the dataset's own maps were made with**. Feeding the same AIF and the same time axis to this
  implementation makes a difference in the maps a difference in the method.

The set is not one protocol: nine cases are sampled at 0.50 s over 44 s (89 points) and six at
2.81 s over 47.8 s (18 points). Case-level results are never pooled across the two, which is
recorded as amendment 5 in ``paper/PROTOCOL.md``.
"""

from __future__ import annotations

import glob
import os
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

ROOT_VARIABLE = "UNITOBRAIN_ROOT"
FILTERED = "_Registered_Filtered_3mm_20HU"
REGISTERED = "_Registered"
MAPS = FILTERED + "_Maps"

#: Tissue admitted into a hemispheric summary: plausible baseline attenuation and a bolus that
#: actually arrived. Deliberately loose -- it is a mask, not a segmentation.
BASELINE_MIN, BASELINE_MAX, MIN_PEAK = -10.0, 200.0, 5.0


def root() -> str:
    """Where the extracted UniToBrain ``test`` folder is, from the environment only."""
    value = os.environ.get(ROOT_VARIABLE, "").strip().strip('"')
    if not value:
        raise RuntimeError(
            f"{ROOT_VARIABLE} is not set. Point it at the directory holding the extracted "
            "UniToBrain test folder (the one containing MOL-001, MOL-001_Registered and so "
            "on). The dataset is public but is not redistributed with this repository; see "
            "the module docstring for the exact command."
        )
    if not os.path.isdir(value):
        raise RuntimeError(f"{ROOT_VARIABLE} is set to {value!r}, which is not a directory")
    return value


def cases() -> list[str]:
    """Every case directory, excluding the derived ones whose names carry a suffix."""
    base = root()
    return sorted(
        name for name in os.listdir(base)
        if "_" not in name and os.path.isdir(os.path.join(base, name))
    )


@dataclass(frozen=True)
class Acquisition:
    """One case: the 4-D volume, the time axis, and the arterial input the dataset used."""

    case: str
    volume: np.ndarray          # (n_times, n_slices, rows, cols), Hounsfield units
    times: np.ndarray           # seconds
    shipped_aif: np.ndarray     # enhancement, the curve the reference maps were made with
    slice_locations: list[float]

    @property
    def dt(self) -> float:
        return float(np.mean(np.diff(self.times)))

    @property
    def window(self) -> tuple[float, float]:
        return float(self.times[0]), float(self.times[-1])

    def metadata(self) -> dict:
        """The dictionary ctp_core's map generator expects."""
        return {
            "n_times": int(self.volume.shape[0]),
            "rows": int(self.volume.shape[2]),
            "cols": int(self.volume.shape[3]),
            "time_seconds": list(map(float, self.times)),
        }


def _read_series(folder: str) -> tuple[np.ndarray, list[float]]:
    import pydicom  # imported here so the module can be read without pydicom installed

    by_time: defaultdict[int, dict[float, np.ndarray]] = defaultdict(dict)
    for path in sorted(glob.glob(os.path.join(folder, "*.dcm"))):
        data = pydicom.dcmread(path)
        slope = float(getattr(data, "RescaleSlope", 1.0))
        intercept = float(getattr(data, "RescaleIntercept", 0.0))
        by_time[int(data.AcquisitionNumber)][float(data.SliceLocation)] = (
            data.pixel_array.astype(np.float32) * slope + intercept
        )
    if not by_time:
        raise FileNotFoundError(f"no DICOM files under {folder}")
    stamps = sorted(by_time)
    locations = sorted(by_time[stamps[0]])
    # A ragged volume would be silently wrong rather than noisy, so check it here.
    for stamp in stamps:
        if sorted(by_time[stamp]) != locations:
            raise ValueError(
                f"{folder}: acquisition {stamp} has {len(by_time[stamp])} slices, "
                f"expected {len(locations)}"
            )
    volume = np.stack([np.stack([by_time[s][z] for z in locations]) for s in stamps])
    return volume, locations


def load(case: str, *, filtered: bool = True) -> Acquisition:
    """One case, with the time axis and arterial input the dataset shipped beside its maps."""
    base = root()
    suffix = FILTERED if filtered else REGISTERED
    volume, locations = _read_series(os.path.join(base, case + suffix))
    with open(os.path.join(base, case + MAPS + ".txt"), encoding="utf-8") as handle:
        times = np.array([float(x) for x in handle.readline().split()])
        aif = np.array([float(x) for x in handle.readline().split()])
    if times.size != volume.shape[0] or aif.size != volume.shape[0]:
        raise ValueError(
            f"{case}: {volume.shape[0]} acquisitions but {times.size} times and {aif.size} "
            "arterial samples"
        )
    return Acquisition(case=case, volume=volume, times=times, shipped_aif=aif,
                       slice_locations=locations)


def reference_map(case: str, series: str) -> list[np.ndarray]:
    """A shipped reference map, slice by slice. ``series`` is e.g. ``NLR_TTP``."""
    import pydicom  # noqa: PLC0415

    out = []
    folder = os.path.join(root(), case + MAPS, series)
    for path in sorted(glob.glob(os.path.join(folder, "*.dcm"))):
        data = pydicom.dcmread(path)
        out.append(data.pixel_array.astype(np.float64) * float(data.RescaleSlope)
                   + float(data.RescaleIntercept))
    if not out:
        raise FileNotFoundError(f"no reference map under {folder}")
    return out


def tissue_mask(slab: np.ndarray) -> np.ndarray:
    """Tissue in one slice of a 4-D volume, as (n_times, rows, cols)."""
    baseline = slab[:2].mean(axis=0)
    peak = (slab - baseline[None]).max(axis=0)
    return (baseline > BASELINE_MIN) & (baseline < BASELINE_MAX) & (peak > MIN_PEAK)


def busiest_slice(volume: np.ndarray) -> int:
    """The slice with the most admitted tissue — the stated rule for choosing one per case."""
    return int(np.argmax([tissue_mask(volume[:, i]).sum() for i in range(volume.shape[1])]))
