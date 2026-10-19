"""Prove the driver tests by injection.

    python paper/analysis/prove_driver_gates.py

A check nobody has seen fail is not evidence (AGENTS.md section 7). Each mutation below is a
defect the test module claims to catch. The suite is copied to a temporary directory, the
mutation applied there, and the suite run: the named test must fail, and it must be the one that
fails.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

SOURCE = pathlib.Path(__file__).resolve().parent

MUTATIONS = [
    (
        "split at the image centre instead of the mask centroid",
        "run_screen.py",
        "    split = hemispheres(mask)",
        "    class _Fixed:\n"
        "        pass\n"
        "    split = _Fixed()\n"
        "    centre = ttp.shape[1] // 2\n"
        "    split.midline = centre\n"
        "    split.left = mask.copy(); split.left[:, centre:] = False\n"
        "    split.right = mask.copy(); split.right[:, :centre] = False",
        "test_the_midline_follows_an_off_centre_head",
    ),
    (
        "drop the per-side minimum and keep only the total",
        "run_screen.py",
        "    if split.left.sum() < MIN_VOXELS or split.right.sum() < MIN_VOXELS:\n"
        "        return None",
        "    pass",
        "test_a_slice_with_too_little_tissue_on_one_side_is_not_compared",
    ),
    (
        "admit background zeros as fast tissue (in both screens, so the invariant stays green)",
        ("run_screen.py", "run_reference.py"),
        "TTP_MIN, TTP_MAX = 0.5, 20.0",
        "TTP_MIN, TTP_MAX = -1.0, 20.0",
        "test_background_zeros_are_not_admitted_as_fast_tissue",
    ),
    (
        "admit vessels by removing the upper bound (in both screens)",
        ("run_screen.py", "run_reference.py"),
        "TTP_MIN, TTP_MAX = 0.5, 20.0",
        "TTP_MIN, TTP_MAX = 0.5, 1e9",
        "test_vessels_are_excluded_by_the_upper_bound",
    ),
    (
        "cut the clinical sample to a hundred voxels per hemisphere",
        "run_clinical.py",
        "N_PER_HEMISPHERE = 500",
        "N_PER_HEMISPHERE = 100",
        "test_the_standard_error_claimed_in_the_docstring_holds",
    ),
    (
        "drop the clinical sampling interval from the synthetic grid",
        "run_synthetic.py",
        "DT_LEVELS = [0.5, 1.0, 2.0, 2.81, 4.0]",
        "DT_LEVELS = [0.5, 1.0, 2.0, 4.0]",
        "test_both_clinical_sampling_intervals_are_on_the_grid",
    ),
    (
        "take ten repeats instead of two hundred",
        "run_synthetic.py",
        "N_REPEATS = 200",
        "N_REPEATS = 10",
        "test_the_repeat_count_resolves_the_floor_it_is_used_to_test",
    ),
    (
        "let the propagation grid stop below the saturation point",
        "run_propagation.py",
        "RATIOS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 6.97, 10.47]",
        "RATIOS = [1.0, 2.0, 3.0]",
        "test_the_measured_clinical_errors_are_on_the_grid",
    ),
    (
        "let the two screens disagree about which tissue they admit",
        "run_reference.py",
        "TTP_MIN, TTP_MAX = 0.5, 20.0",
        "TTP_MIN, TTP_MAX = 0.5, 30.0",
        "test_the_ttp_windows_are_identical",
    ),
    (
        "admit a hemisphere summarised from a handful of values",
        "run_clinical.py",
        "MIN_ADMITTED = 100",
        "MIN_ADMITTED = 3",
        "test_a_hemisphere_is_not_summarised_from_a_handful_of_values",
    ),
    (
        "take the busiest slice as the first one instead of the one with the most tissue",
        "unitobrain.py",
        "    return int(np.argmax([tissue_mask(volume[:, i]).sum() for i in range(volume.shape[1])]))",
        "    return 0",
        "test_the_busiest_slice_is_the_one_with_the_most_tissue",
    ),
    (
        "admit tissue the bolus never reached",
        "unitobrain.py",
        "BASELINE_MIN, BASELINE_MAX, MIN_PEAK = -10.0, 200.0, 5.0",
        "BASELINE_MIN, BASELINE_MAX, MIN_PEAK = -10.0, 200.0, -1e9",
        "test_the_tissue_mask_needs_a_bolus_to_have_arrived",
    ),
    (
        "admit air and bone as tissue",
        "unitobrain.py",
        "BASELINE_MIN, BASELINE_MAX, MIN_PEAK = -10.0, 200.0, 5.0",
        "BASELINE_MIN, BASELINE_MAX, MIN_PEAK = -1e9, 1e9, 5.0",
        "test_air_and_bone_are_not_admitted",
    ),
    (
        "ignore the environment and return one machine's dataset path",
        "unitobrain.py",
        '    value = os.environ.get(ROOT_VARIABLE, "").strip().strip(\'"\')',
        '    value = "/mnt/one-particular-machine/UniToBrain/test_set/test"',
        "test_the_root_comes_from_the_environment",
    ),
    (
        "fall back to a hard-coded default when the environment says nothing",
        "unitobrain.py",
        '    value = os.environ.get(ROOT_VARIABLE, "").strip().strip(\'"\')',
        '    value = os.environ.get(ROOT_VARIABLE) or os.path.dirname(__file__)',
        "test_an_unset_root_is_an_error_that_names_the_variable",
    ),
    (
        "accept a root that is not a directory",
        "unitobrain.py",
        "    if not os.path.isdir(value):\n"
        "        raise RuntimeError(f\"{ROOT_VARIABLE} is set to {value!r}, which is not a "
        "directory\")",
        "    pass",
        "test_a_root_that_is_not_a_directory_is_refused",
    ),
    (
        "write one machine's path back into a driver",
        "run_screen.py",
        "import unitobrain  # noqa: E402",
        "import unitobrain  # noqa: E402\n\n_LOCAL = r\"D:" + chr(92) + "wherever" + chr(92)
        + "UniToBrain\"",
        "test_no_machine_specific_path_is_committed",
    ),
]


def run(folder: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", ".", "-v"],
        cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def failed_tests(output: str) -> set[str]:
    names = set()
    for line in output.splitlines():
        for marker in ("FAIL: ", "ERROR: "):
            if line.startswith(marker):
                names.add(line[len(marker):].split(" ")[0])
    return names


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        clean = pathlib.Path(temp) / "clean"
        shutil.copytree(SOURCE, clean, ignore=shutil.ignore_patterns("__pycache__"))
        baseline = run(clean)
        if baseline.returncode != 0:
            print("the unmutated suite does not pass, so nothing below means anything")
            print(baseline.stdout[-4000:], baseline.stderr[-4000:])
            return 1
        total = baseline.stderr.count("... ok")
        print(f"baseline: {total} tests pass\n")

        bad = 0
        for description, filename, before, after, expected in MUTATIONS:
            work = pathlib.Path(temp) / "work"
            if work.exists():
                shutil.rmtree(work)
            shutil.copytree(clean, work, ignore=shutil.ignore_patterns("__pycache__"))
            names = (filename,) if isinstance(filename, str) else filename
            broken = False
            for name in names:
                target = work / name
                text = target.read_text(encoding="utf-8")
                if text.count(before) != 1:
                    print(f"SETUP ERROR  {description}: the text to mutate appears "
                          f"{text.count(before)} times in {name}")
                    broken = True
                    break
                target.write_text(text.replace(before, after), encoding="utf-8")
            if broken:
                bad += 1
                continue

            result = run(work)
            caught = failed_tests(result.stderr)
            if result.returncode == 0:
                print(f"MISSED       {description}\n             no test failed")
                bad += 1
            elif expected in caught:
                others = sorted(n for n in caught if n != expected)
                extra = f"  (also {', '.join(others)})" if others else ""
                print(f"caught       {description}\n             by {expected}{extra}")
            else:
                print(f"WRONG TEST   {description}\n             expected {expected}, "
                      f"got {sorted(caught) or 'a collection error'}")
                if not caught:
                    print(result.stderr[-1500:])
                bad += 1

        print(f"\n{len(MUTATIONS) - bad} of {len(MUTATIONS)} injected defects were caught "
              "by the test that claims to catch them")
        return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
