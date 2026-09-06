"""The release metadata must agree with itself and with what the archive holds.

A reader of the published article follows two things: a repository URL and an archived
DOI. Zenodo mints two DOIs per software record -- a concept DOI that follows whichever
release is newest, and a version DOI frozen to one snapshot -- and they differ by a few
digits in the middle of a long number. This repository is the reason that distinction is
not academic here: the release the concept DOI pointed at stopped running when NumPy 2
removed ``np.trapz``, so "the latest version" and "the version the paper measured" were,
for a while, different pieces of software with different behaviour.

That was fixed in v0.1.1 and archived, but the README went on telling a reader the version
DOI was "minted on release" for the four days after it had in fact been minted, while the
submitted manuscript cited it correctly. The front page of a repository is where a reviewer
looks first.

CITATION.cff is parsed textually rather than with PyYAML on purpose: CI installs
requirements-core.txt and pytest, and nothing else. A gate that skips for a missing
dependency is a gate that does not run.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CITATION = REPO / "CITATION.cff"
README = REPO / "README.md"

REPO_URL = "https://github.com/Institute-of-One/ctp-core"

DOI = re.compile(r"10\.5281/zenodo\.\d+")


def _citation():
    """Every DOI identifier in CITATION.cff, as (value, description) pairs."""
    text = CITATION.read_text(encoding="utf-8")
    pairs = re.findall(
        r'-\s+type:\s*doi\s*\n\s*value:\s*"([^"]+)"\s*\n\s*description:\s*"([^"]+)"',
        text,
    )
    assert pairs, "CITATION.cff declares no DOI identifier at all"
    return pairs


def _version():
    text = CITATION.read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"?([^"\n]+)"?\s*$', text, flags=re.MULTILINE)
    assert match, "CITATION.cff declares no version"
    return match.group(1).strip()


def _labelled(word):
    matches = [value for value, description in _citation() if word in description.lower()]
    assert len(matches) == 1, (
        "exactly one DOI in CITATION.cff must describe itself as the %s DOI; "
        "found %d, and nothing downstream can tell them apart" % (word, len(matches))
    )
    return matches[0]


def test_citation_declares_both_the_concept_and_the_version_doi():
    """One DOI on its own leaves a citation manager guessing which kind it is."""
    concept = _labelled("concept")
    version = _labelled("version doi")
    assert concept != version, "the concept and version DOIs are the same record"


def test_the_version_doi_names_the_version_this_repository_declares():
    description = next(
        description
        for value, description in _citation()
        if value == _labelled("version doi")
    )
    assert _version() in description, (
        "CITATION.cff describes the version DOI without naming v%s, the version it "
        "declares: %r" % (_version(), description)
    )


def test_the_readme_gives_the_version_doi_rather_than_a_promise_of_one():
    """It said "minted on release" for four days after the DOI was minted.

    A placeholder is indistinguishable from a fact until someone tries to follow it,
    and the person most likely to try is a reviewer holding the manuscript that cites
    the number the README says does not exist yet.
    """
    line = next(
        (line for line in README.read_text(encoding="utf-8").splitlines()
         if "this release" in line.lower() and "doi" in line.lower()),
        None,
    )
    assert line is not None, "the README no longer names the DOI for this release"
    assert DOI.search(line), (
        "the README promises a DOI for this release instead of giving one: %r" % line
    )
    assert _labelled("version doi") in line, (
        "the README's release DOI is not the version DOI CITATION.cff declares: %r" % line
    )


def test_the_readme_badge_is_the_concept_doi():
    """A badge should follow the newest release; a citation should not.

    These are the two correct uses of the two DOIs, and swapping them is the whole
    defect: a frozen badge goes stale, and a moving citation goes wrong.
    """
    badge = next(
        (line for line in README.read_text(encoding="utf-8").splitlines()
         if "zenodo.org/badge" in line),
        None,
    )
    assert badge is not None, "the README carries no Zenodo badge"
    assert _labelled("concept") in badge, (
        "the badge does not show the concept DOI: %r" % badge
    )


def test_the_repository_url_is_declared_and_singular():
    """The archive travels without the repository unless the README says where it is.

    The manuscript sends a reader to this repository; the README named GitHub in prose
    and gave no address, so a copy of it downloaded from Zenodo led nowhere back.
    """
    citation = CITATION.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert 'repository-code: "%s"' % REPO_URL in citation
    assert REPO_URL in readme, "the README does not say where the source code lives"
    organisations = set(re.findall(r"github\.com/([A-Za-z0-9_.-]+)", readme))
    assert organisations == {"Institute-of-One"}, (
        "unexpected GitHub organisations in the README: %s" % sorted(organisations)
    )
