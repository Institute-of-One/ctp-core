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
import math
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
    acquisitions: list[int]     # the DICOM acquisition numbers, in the volume's order

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


def _read_series(folder: str) -> tuple[np.ndarray, list[float], list[int]]:
    import pydicom  # imported here so the module can be read without pydicom installed

    by_time: defaultdict[int, dict[float, np.ndarray]] = defaultdict(dict)
    for path in sorted(glob.glob(os.path.join(folder, "*.dcm"))):
        data = pydicom.dcmread(path)
        slope = float(getattr(data, "RescaleSlope", 1.0))
        intercept = float(getattr(data, "RescaleIntercept", 0.0))
        stamp, location = int(data.AcquisitionNumber), float(data.SliceLocation)
        # Two files claiming the same acquisition and the same position would otherwise have
        # one silently overwrite the other, leaving a volume of the right shape built from the
        # wrong images -- which no later check could see. A review found this.
        if location in by_time[stamp]:
            raise ValueError(
                f"{folder}: two files give acquisition {stamp} at slice location {location}; "
                f"the second is {os.path.basename(path)}"
            )
        by_time[stamp][location] = (
            data.pixel_array.astype(np.float32) * slope + intercept
        )
    if not by_time:
        raise FileNotFoundError(f"no DICOM files under {folder}")
    stamps = sorted(by_time)
    # Sorting the acquisition numbers and then dropping them would let a set with an
    # acquisition missing from the middle be stacked into a volume that is shorter but
    # otherwise well formed, and then handed the dataset's full time axis. A reviewer pointed
    # this out: equal shapes between two series do not establish that they cover the same
    # acquisitions. They are required to run without a gap, and they are returned.
    if stamps != list(range(stamps[0], stamps[0] + len(stamps))):
        missing = sorted(set(range(stamps[0], stamps[-1] + 1)) - set(stamps))
        raise ValueError(
            f"{folder}: acquisitions {stamps[0]} to {stamps[-1]} with "
            f"{len(missing)} missing ({missing[:5]}); the time axis could not be assigned")
    locations = sorted(by_time[stamps[0]])
    # A ragged volume would be silently wrong rather than noisy, so check it here.
    for stamp in stamps:
        if sorted(by_time[stamp]) != locations:
            raise ValueError(
                f"{folder}: acquisition {stamp} has {len(by_time[stamp])} slices, "
                f"expected {len(locations)}"
            )
    volume = np.stack([np.stack([by_time[s][z] for z in locations]) for s in stamps])
    return volume, locations, stamps


def load(case: str, *, filtered: bool = True) -> Acquisition:
    """One case, with the time axis and arterial input the dataset shipped beside its maps."""
    base = root()
    suffix = FILTERED if filtered else REGISTERED
    volume, locations, acquisitions = _read_series(os.path.join(base, case + suffix))
    with open(os.path.join(base, case + MAPS + ".txt"), encoding="utf-8") as handle:
        times = np.array([float(x) for x in handle.readline().split()])
        aif = np.array([float(x) for x in handle.readline().split()])
    if times.size != volume.shape[0] or aif.size != volume.shape[0]:
        raise ValueError(
            f"{case}: {volume.shape[0]} acquisitions but {times.size} times and {aif.size} "
            "arterial samples"
        )
    return Acquisition(case=case, volume=volume, times=times, shipped_aif=aif,
                       slice_locations=locations, acquisitions=acquisitions)


@dataclass(frozen=True)
class ReferenceSeries:
    """A shipped reference map, ordered by slice location, with those locations."""

    case: str
    series: str
    images: list[np.ndarray]
    slice_locations: list[float]

    def __len__(self) -> int:
        return len(self.images)

    def at_slice(self, index: int, expected_location: float | None = None) -> np.ndarray:
        """The map at the volume's slice ``index``, checked against its physical position.

        A review pointed out that the volume is ordered by slice location while this series
        used to be ordered by file name, and that the acquisition's slice index was then used
        to index it. On this dataset the two orders happen to coincide for all 15 cases -- it
        was checked -- but nothing made them, so the position is now verified rather than
        assumed.
        """
        if not 0 <= index < len(self.images):
            raise IndexError(
                f"{self.case}/{self.series}: slice {index} of {len(self.images)}")
        if expected_location is not None:
            found = self.slice_locations[index]
            # NaN compares false against everything, so a non-finite position used to slip
            # through the comparison below and defeat the whole check. A reviewer found it.
            if not (math.isfinite(found) and math.isfinite(expected_location)):
                raise ValueError(
                    f"{self.case}/{self.series}: slice {index} is at {found} and the volume's "
                    f"at {expected_location}; a non-finite position cannot be checked")
            if abs(found - expected_location) > 1e-6:
                raise ValueError(
                    f"{self.case}/{self.series}: slice {index} of the reference is at "
                    f"{found}, but the volume's slice {index} is at {expected_location}; "
                    "the two series are not in the same order"
                )
        return self.images[index]


def reference_map(case: str, series: str) -> ReferenceSeries:
    """A shipped reference map, ordered by slice location. ``series`` is e.g. ``NLR_TTP``."""
    import pydicom  # noqa: PLC0415

    folder = os.path.join(root(), case + MAPS, series)
    found = []
    for path in sorted(glob.glob(os.path.join(folder, "*.dcm"))):
        data = pydicom.dcmread(path)
        image = (data.pixel_array.astype(np.float64) * float(data.RescaleSlope)
                 + float(data.RescaleIntercept))
        found.append((float(data.SliceLocation), image))
    if not found:
        raise FileNotFoundError(f"no reference map under {folder}")
    locations = [z for z, _ in found]
    if len(set(locations)) != len(locations):
        raise ValueError(f"{folder}: two reference slices share a slice location")
    found.sort(key=lambda pair: pair[0])
    return ReferenceSeries(case=case, series=series,
                           images=[image for _, image in found],
                           slice_locations=[z for z, _ in found])


def tissue_mask(slab: np.ndarray) -> np.ndarray:
    """Tissue in one slice of a 4-D volume, as (n_times, rows, cols).

    Every admitted voxel must be finite throughout. A reviewer pointed out that an infinite
    sample satisfied ``peak > MIN_PEAK`` and was taken as evidence that a bolus had arrived:
    such a voxel would then have been counted by :func:`busiest_slice` and could have been
    drawn into a hemispheric mean, where one infinity is enough to destroy the result.
    """
    finite = np.isfinite(slab).all(axis=0)
    baseline = slab[:2].mean(axis=0)
    with np.errstate(invalid="ignore"):
        peak = (slab - baseline[None]).max(axis=0)
        admitted = ((baseline > BASELINE_MIN) & (baseline < BASELINE_MAX)
                    & (peak > MIN_PEAK) & np.isfinite(peak))
    return admitted & finite


def busiest_slice(volume: np.ndarray) -> int:
    """The slice with the most admitted tissue — the stated rule for choosing one per case."""
    return int(np.argmax([tissue_mask(volume[:, i]).sum() for i in range(volume.shape[1])]))
