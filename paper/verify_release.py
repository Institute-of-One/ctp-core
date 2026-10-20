"""Unpack the prospective release into a fresh environment and run what the paper promises.

    python paper/verify_release.py

Run this before cutting a tag. It takes a few minutes, because installing into an empty
environment is the point.

A DOI-cited release of this repository once stopped working: np.trapz was removed by NumPy 2,
the dependency had no upper bound, and nothing noticed because the tests ran in an environment
that already had the old NumPy. There is no commit to blame for that defect -- it arrived from
outside -- and the only thing that catches it is installing the archive as a stranger would.

So: export the tree exactly as `git archive` would ship it, build a virtual environment with
nothing in it, install the declared dependencies, and run the paths the data availability
statement promises a reader can run. Nothing here uses the working tree's packages.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]

#: What the data availability statement says a reader can do with the archive.
PROMISED = [
    ("the measurement tests", ["-m", "unittest", "discover", "-s", "paper/analysis"]),
    ("the package tests", ["-m", "pytest", "tests", "-q"]),
    ("the figures, from the archived results", ["paper/make_figures.py"]),
    ("the manuscript, from the same results", ["paper/build_manuscript.py"]),
    ("the deterministic examples", ["examples/run_synthetic_demo.py"]),
]


def run(python: str, args: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run([python, *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp)
        tree = root / "archive"
        tree.mkdir()

        # Exactly what the release will contain: tracked files at HEAD, nothing ignored.
        export = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=REPO,
                                capture_output=True)
        if export.returncode:
            print("git archive failed:", export.stderr.decode(errors="replace"))
            return 1
        tar = root / "release.tar"
        tar.write_bytes(export.stdout)
        shutil.unpack_archive(str(tar), str(tree), format="tar")
        files = [p for p in tree.rglob("*") if p.is_file()]
        print(f"the archive holds {len(files)} files, {sum(p.stat().st_size for p in files) / 1e6:.1f} MB")

        # Every results file the manuscript cites must be in it, or a reader cannot rebuild.
        results = tree / "paper" / "results"
        wanted = ["aif_factor.json", "aif_propagation.json", "synthetic_f1_f4.json",
                  "f1_f2_clinical.json", "clinical_vs_reference.json", "figure_case.json",
                  "mol001_maps.npz"]
        missing = [name for name in wanted if not (results / name).is_file()]
        if missing:
            print(f"the archive is missing results the manuscript cites: {missing}")
            return 1
        print(f"every one of the {len(wanted)} results files the manuscript cites is in it")

        print("\nbuilding a virtual environment with nothing in it")
        venv = root / "venv"
        made = subprocess.run([sys.executable, "-m", "venv", str(venv)],
                              capture_output=True, text=True)
        if made.returncode:
            print("could not create the venv:", made.stderr)
            return 1
        python = str(venv / ("Scripts" if os.name == "nt" else "bin") /
                     ("python.exe" if os.name == "nt" else "python"))

        print("installing requirements-core.txt, and nothing else")
        install = run(python, ["-m", "pip", "install", "--quiet", "-r",
                               "requirements-core.txt", "pytest"], tree)
        if install.returncode:
            print("the declared dependencies do not install:")
            print(install.stdout[-2000:], install.stderr[-2000:])
            return 1
        versions = run(python, ["-c", "import numpy, scipy, matplotlib; "
                                "print(numpy.__version__, scipy.__version__, "
                                "matplotlib.__version__)"], tree)
        print(f"  installed numpy/scipy/matplotlib {versions.stdout.strip()}")

        failed = 0
        print()
        for description, args in PROMISED:
            result = run(python, args, tree)
            if result.returncode == 0:
                print(f"ok    {description}")
            else:
                failed += 1
                print(f"FAIL  {description}")
                tail = (result.stdout + result.stderr).strip().splitlines()[-6:]
                for line in tail:
                    print(f"      {line}")

        print()
        if failed:
            print(f"{failed} of {len(PROMISED)} promised paths do not run from the archive")
            return 1
        print(f"all {len(PROMISED)} promised paths run from a clean archive in a fresh "
              "environment")
        print("The release candidate does what the data availability statement says it does.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
