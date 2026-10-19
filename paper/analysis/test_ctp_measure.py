"""Tests for the measurement logic the manuscript reports.

Standard ``unittest`` on purpose: the repository's own suite is pytest-style, but the shared
Codex/Claude cross-check runs standard unittest only, and the code that produces a paper's
numbers is exactly the code that should go through it.

Each test states the property it fixes. Two of them inject a known defect and check that it is
caught, because a check nobody has seen fail is not evidence.
"""

from __future__ import annotations

import math
import pathlib
import sys
import unittest

import numpy as np

# The module under test sits beside this file, which is also how the cross-check snapshot
# arranges them: its discovery command is frozen as `-m unittest discover -s . -v`.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from ctp_measure import (  # noqa: E402
    MAX_AREA,
    MIN_AREA,
    MIN_DENSITY,
    FitRejection,
    cbv_from_areas,
    curve_area,
    fitted_peak_time,
    hemispheres,
    quantisation_floor,
    sampled_peak_time,
)


class SampledPeakTime(unittest.TestCase):
    """The fit-free path can only return a value that was sampled."""

    def test_result_is_always_on_the_sampling_grid(self):
        times = np.arange(0.0, 50.0, 2.81)
        rng = np.random.default_rng(0)
        for _ in range(200):
            curve = rng.normal(size=times.size)
            self.assertIn(sampled_peak_time(times, curve), set(times.tolist()))

    def test_it_finds_an_unambiguous_peak(self):
        times = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        curve = np.array([0.0, 1.0, 9.0, 1.0, 0.0])
        self.assertEqual(sampled_peak_time(times, curve), 2.0)

    def test_mismatched_shapes_are_refused(self):
        with self.assertRaises(ValueError):
            sampled_peak_time(np.arange(5.0), np.arange(4.0))

    def test_empty_and_two_dimensional_input_are_refused(self):
        with self.assertRaises(ValueError):
            sampled_peak_time(np.array([]), np.array([]))
        with self.assertRaises(ValueError):
            sampled_peak_time(np.zeros((2, 3)), np.zeros((2, 3)))

    def test_a_nan_sample_is_refused_rather_than_reported_as_the_peak(self):
        # np.argmax returns the index of the first NaN, so without the guard a single bad
        # sample is silently reported as the time to peak.
        times = np.array([0.0, 1.0, 2.0])
        with self.assertRaises(ValueError):
            sampled_peak_time(times, np.array([0.0, float("nan"), 5.0]))


class QuantisationFloor(unittest.TestCase):
    """The floor is dt/sqrt(12), and the sampled path actually sits on it."""

    def test_closed_form(self):
        self.assertAlmostEqual(quantisation_floor(2.81), 2.81 / math.sqrt(12.0), places=12)

    def test_a_non_positive_interval_is_refused(self):
        for bad in (0.0, -1.0):
            with self.assertRaises(ValueError):
                quantisation_floor(bad)

    def test_the_sampled_path_itself_sits_on_the_floor(self):
        # A review noted that the previous version of this test rounded with NumPy and never
        # called sampled_peak_time, so it established a property of np.round rather than of the
        # function the manuscript uses. This drives the function.
        #
        # A triangular peak on a fine grid is sampled onto a coarse one; the true peak time is
        # uniform within a cell, which is the situation the floor describes.
        dt = 2.81
        times = np.arange(0.0, 60.0, dt)
        rng = np.random.default_rng(20261019)
        errors = []
        for _ in range(4000):
            truth = float(rng.uniform(10.0, 40.0))
            curve = np.maximum(0.0, 100.0 - 8.0 * np.abs(times - truth))
            errors.append(sampled_peak_time(times, curve) - truth)
        self.assertAlmostEqual(float(np.std(errors, ddof=1)), quantisation_floor(dt), delta=0.05)
        self.assertLess(abs(float(np.mean(errors))), 0.05)


class ValidityRule(unittest.TestCase):
    """A fitted peak outside the sampled window is not a measurement."""

    WINDOW = (0.0, 47.77)

    def test_a_peak_inside_the_window_is_admitted(self):
        value, reason = fitted_peak_time(22.5, success=True, window=self.WINDOW)
        self.assertEqual(value, 22.5)
        self.assertIsNone(reason)

    def test_the_window_is_inclusive_at_both_ends(self):
        for edge in self.WINDOW:
            value, reason = fitted_peak_time(edge, success=True, window=self.WINDOW)
            self.assertEqual(value, edge)
            self.assertIsNone(reason)

    def test_an_unsuccessful_fit_is_rejected_even_with_a_plausible_value(self):
        value, reason = fitted_peak_time(22.5, success=False, window=self.WINDOW)
        self.assertIsNone(value)
        self.assertEqual(reason, FitRejection.FAILED)

    def test_a_non_finite_peak_is_rejected(self):
        for bad in (float("nan"), float("inf"), None):
            value, reason = fitted_peak_time(bad, success=True, window=self.WINDOW)
            self.assertIsNone(value)
            self.assertEqual(reason, FitRejection.FAILED)

    def test_the_defect_this_rule_exists_for_is_caught(self):
        # Injected: the values fit_gamma_variate actually returned on MOL-002 while reporting
        # success -- an acquisition spanning 0 to 44 s produced peaks at -32.47 s and +918.68 s.
        # Without this rule they entered the hemispheric mean and moved it by tens of seconds.
        window = (0.0, 44.0)
        for observed in (-32.47, 918.68, 44.01, -0.01):
            value, reason = fitted_peak_time(observed, success=True, window=window)
            self.assertIsNone(value, f"{observed} should not have been admitted")
            self.assertEqual(reason, FitRejection.OUTSIDE_WINDOW)

    def test_a_reversed_window_is_refused(self):
        with self.assertRaises(ValueError):
            fitted_peak_time(10.0, success=True, window=(40.0, 10.0))


class AreaAndVolume(unittest.TestCase):
    """CBV is a ratio of areas, so an error in the arterial area passes straight through."""

    def test_area_of_a_triangle(self):
        times = np.array([0.0, 1.0, 2.0])
        self.assertAlmostEqual(curve_area(times, np.array([0.0, 2.0, 0.0])), 2.0, places=12)

    def test_the_time_axis_scales_the_area(self):
        # A review noted that every area test used unit spacing, so none of them could tell
        # integrating over time apart from summing ordinates. Real sampling here is 0.50 s or
        # 2.81 s, never 1 s.
        curve = np.array([0.0, 3.0, 0.0])
        self.assertAlmostEqual(curve_area(np.array([0.0, 2.0, 4.0]), curve), 6.0, places=12)
        self.assertAlmostEqual(curve_area(np.array([0.0, 0.5, 1.0]), curve), 1.5, places=12)
        self.assertAlmostEqual(curve_area(np.array([0.0, 2.81, 5.62]), curve), 3.0 * 2.81,
                               places=12)

    def test_unequal_spacing_is_honoured_segment_by_segment(self):
        # Doubling only the second interval must add only that segment's area.
        curve = np.array([0.0, 4.0, 0.0])
        narrow = curve_area(np.array([0.0, 1.0, 2.0]), curve)
        wide = curve_area(np.array([0.0, 1.0, 3.0]), curve)
        self.assertAlmostEqual(narrow, 4.0, places=12)
        self.assertAlmostEqual(wide, 2.0 + 4.0, places=12)

    def test_negative_enhancement_does_not_subtract_area(self):
        times = np.array([0.0, 1.0, 2.0])
        self.assertAlmostEqual(curve_area(times, np.array([0.0, -5.0, 0.0])), 0.0, places=12)

    def test_a_segment_crossing_zero_contributes_only_its_positive_triangle(self):
        # Injected by both reviewers: clipping the samples and then integrating returns 0.5
        # here, because clipping moves the crossing from t = 0.5 to the sample. The line from
        # (0, -1) to (1, 1) is above zero on the second half only, so the area is 0.25.
        self.assertAlmostEqual(
            curve_area(np.array([0.0, 1.0]), np.array([-1.0, 1.0])), 0.25, places=12)
        self.assertAlmostEqual(
            curve_area(np.array([0.0, 1.0]), np.array([1.0, -1.0])), 0.25, places=12)

    def test_the_mutant_that_clips_the_net_integral_is_rejected(self):
        # The reviewer's mutant: `max(0.0, trapezoid(curve, times))`. On this curve the net
        # integral is zero, so the mutant returns 0.0 and is distinguishable.
        #
        # The expected value is derived here rather than taken from the review, which asserted
        # 2.0: segment 0-1 is a trapezoid of area (0+2)/2 = 1.0; segment 1-2 runs from +2 to -2
        # and crosses zero at t = 1.5, contributing a triangle of 0.5 x 2 x 0.5 = 0.5; segment
        # 2-3 lies at or below zero and contributes nothing. The positive area is 1.5.
        times = np.array([0.0, 1.0, 2.0, 3.0])
        curve = np.array([0.0, 2.0, -2.0, 0.0])
        expected = 1.0 + 0.5 * 2.0 * 0.5
        self.assertAlmostEqual(curve_area(times, curve), expected, places=12)
        self.assertAlmostEqual(expected, 1.5, places=12)
        mutant = max(0.0, float(np.trapezoid(curve, times)))
        self.assertNotAlmostEqual(mutant, expected, places=6)

    def test_non_finite_or_unordered_input_is_refused(self):
        with self.assertRaises(ValueError):
            curve_area(np.array([0.0, 1.0]), np.array([0.0, float("nan")]))
        with self.assertRaises(ValueError):
            curve_area(np.array([1.0, 0.0]), np.array([1.0, 1.0]))

    def test_cbv_has_the_absolute_value_the_definition_gives(self):
        # Ratio tests alone cannot see a missing density correction or a missing factor of 100,
        # because a common multiplier cancels. Both reviewers demonstrated the mutant.
        self.assertAlmostEqual(cbv_from_areas(500.0, 1000.0), 500.0 / 1000.0 / 1.04 * 100.0,
                               places=10)
        self.assertAlmostEqual(cbv_from_areas(2.0, 4.0, density=2.0), 25.0, places=10)

    def test_density_enters_as_a_divisor(self):
        base = cbv_from_areas(500.0, 1000.0, density=1.0)
        self.assertAlmostEqual(cbv_from_areas(500.0, 1000.0, density=2.0), base / 2.0, places=10)

    def test_cbv_scales_exactly_with_the_inverse_arterial_area(self):
        tissue = 500.0
        reference = cbv_from_areas(tissue, 1000.0)
        for factor in (1.5, 2.0, 3.0, 7.0, 10.47):
            understated = cbv_from_areas(tissue, 1000.0 / factor)
            self.assertAlmostEqual(understated / reference, factor, places=10)

    def test_the_measured_clinical_error_inflates_cbv_sevenfold(self):
        # The median arterial-area error measured over the 15 UniToBrain test cases was 6.97.
        reference = cbv_from_areas(500.0, 1000.0)
        self.assertAlmostEqual(cbv_from_areas(500.0, 1000.0 / 6.97) / reference, 6.97, places=10)

    def test_a_non_positive_arterial_area_is_refused(self):
        for bad in (0.0, -1.0):
            with self.assertRaises(ValueError):
                cbv_from_areas(500.0, bad)

    def test_a_non_positive_or_non_finite_density_is_refused(self):
        for bad in (0.0, -1.0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                cbv_from_areas(500.0, 1000.0, density=bad)

    def test_magnitudes_outside_the_supported_domain_are_refused_explicitly(self):
        # Reviews found a different floating-point failure at each attempt to be correct for
        # arbitrary doubles: sequential division overflowing, then the product overflowing and
        # returning a silent zero. The domain is now a precondition rather than a docstring
        # claim, so these refuse instead of returning an unchecked number.
        for tissue, aif, density in ((1e308, 0.5, 1e308), (1e308, 0.5, 1.04),
                                     (500.0, 1e308, 1.04), (500.0, 1000.0, 1e308)):
            with self.assertRaises(ValueError):
                cbv_from_areas(tissue, aif, density=density)

    def test_a_vanishingly_small_arterial_area_is_refused(self):
        # Both reviewers found this independently: bounding the area only from above let a
        # tiny positive area through, and the result then overflowed or was silently lost.
        for aif in (1e-300, 1e-12, MIN_AREA / 2.0, 0.0, -1.0):
            with self.assertRaises(ValueError):
                cbv_from_areas(500.0, aif)

    def test_no_admitted_input_can_overflow(self):
        # With the area and density bounded on both sides the output is bounded above by
        # MAX_AREA / MIN_AREA / MIN_DENSITY * 100, which is finite. Check the extreme corner.
        worst = cbv_from_areas(MAX_AREA, MIN_AREA, density=MIN_DENSITY)
        self.assertTrue(math.isfinite(worst))
        self.assertAlmostEqual(worst, MAX_AREA / MIN_AREA / MIN_DENSITY * 100.0,
                               delta=abs(worst) * 1e-9)

    def test_the_supported_domain_covers_the_measured_values_with_room_to_spare(self):
        # Arterial areas measured on the 15 public cases were 5.0e3 to 1.2e4 HU.s.
        for aif in (5.0e3, 1.2e4):
            self.assertGreater(cbv_from_areas(2.0e3, aif), 0.0)
        self.assertGreaterEqual(MAX_AREA / 1.2e4, 1e7)


class Hemispheres(unittest.TestCase):
    """The split must be disjoint, complete, and taken from the data."""

    def test_disjoint_and_complete(self):
        mask = np.zeros((40, 60), dtype=bool)
        mask[10:30, 5:55] = True
        split = hemispheres(mask)
        self.assertFalse((split.left & split.right).any())
        np.testing.assert_array_equal(split.left | split.right, mask)

    def test_midline_follows_an_off_centre_head(self):
        # A head pushed to the left of the field of view: a fixed centre column would put most
        # of it in one hemisphere. The centroid follows it.
        mask = np.zeros((40, 100), dtype=bool)
        mask[10:30, 10:50] = True
        split = hemispheres(mask)
        self.assertEqual(split.midline, 30)
        self.assertEqual(int(split.left.sum()), int(split.right.sum()))

    def test_a_symmetric_mask_splits_evenly_at_every_width(self):
        # A reviewer found that Python's round() sends an exact .5 centroid to the even
        # integer, so half of all even-width symmetric masks were split one column off
        # balance -- and the test above passed only because its width had the lucky parity.
        # Sweeping the width is what makes the parity irrelevant.
        for width in range(2, 41, 2):
            mask = np.zeros((10, width), dtype=bool)
            mask[2:8, :] = True
            split = hemispheres(mask)
            self.assertEqual(
                int(split.left.sum()), int(split.right.sum()),
                f"width {width} split {split.left.sum()} / {split.right.sum()} "
                f"at midline {split.midline}")

    def test_the_defect_a_fixed_centre_would_cause_is_visible(self):
        # Injected: splitting at the image centre instead of the mask centroid. With the head
        # offset as above, that puts every voxel on one side and the comparison is meaningless.
        mask = np.zeros((40, 100), dtype=bool)
        mask[10:30, 10:50] = True
        fixed_centre = mask.shape[1] // 2
        left_fixed = mask.copy()
        left_fixed[:, fixed_centre:] = False
        self.assertEqual(int(left_fixed.sum()), int(mask.sum()),
                         "the injected defect should sweep the whole head into one hemisphere")
        self.assertNotEqual(hemispheres(mask).midline, fixed_centre)

    def test_the_centroid_is_weighted_by_voxels_not_by_the_bounding_box(self):
        # A review noted that every mask here was an axis-aligned rectangle, for which the
        # voxel-weighted centroid and the bounding-box midpoint coincide, so the tests could
        # not tell them apart. A real head is not a rectangle. This mask is heavy on the left:
        # columns 0-4 carry 9 voxels each and columns 5-9 carry 1, so the weighted centroid is
        # (9*(0+1+2+3+4) + 1*(5+6+7+8+9)) / 50 = 125/50 = 2.5 and the midline is 3, while the
        # bounding-box midpoint would be 4.5.
        mask = np.zeros((10, 10), dtype=bool)
        mask[0:9, 0:5] = True
        mask[0:1, 5:10] = True
        split = hemispheres(mask)
        self.assertEqual(split.midline, 3)
        self.assertNotEqual(split.midline, int(round((0 + 9) / 2)))
        self.assertFalse((split.left & split.right).any())
        np.testing.assert_array_equal(split.left | split.right, mask)

    def test_an_empty_mask_is_refused(self):
        with self.assertRaises(ValueError):
            hemispheres(np.zeros((10, 10), dtype=bool))


if __name__ == "__main__":
    unittest.main()
