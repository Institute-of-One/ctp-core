"""What release the manuscript describes, in one place.

The manuscript, CITATION.cff, the README badge and .zenodo.json all name a version and a DOI,
and they have disagreed before: after v0.1.1 was archived the README went on promising a DOI
"minted on release" for four days, while the submitted manuscript already cited the real one.
Keeping the values here and interpolating them means a release updates one file.

The two DOIs are different things and the distinction is not academic in this repository:

* the **concept** DOI follows whichever release is newest, so it is what a reader should cite
  to mean "this software", and it is what the README badge shows;
* the **version** DOI is frozen to one snapshot, so it is what a *paper* must cite -- the
  release this paper measured, which will not change under a reader. The release the concept
  DOI pointed at once stopped running when NumPy 2 removed ``np.trapz``.

``PENDING`` is what the version DOI holds before the release exists. Zenodo mints it when the
GitHub release is published, so there is an unavoidable gap between tagging and knowing the
number. ``check_manuscript.py`` refuses to pass a manuscript that still says PENDING, which is
what stops that gap from reaching a submission.
"""

from __future__ import annotations

PENDING = "PENDING"

#: The version this manuscript describes. Must equal ctp_core.__version__ and the version in
#: CITATION.cff and .zenodo.json; a test checks that.
VERSION = "0.2.0"

REPOSITORY = "https://github.com/Institute-of-One/ctp-core"

#: Follows the newest release. The README badge, and CITATION.cff's primary identifier.
CONCEPT_DOI = "10.5281/zenodo.20921268"

#: Frozen to this release. Filled in once Zenodo has minted it, which is after the GitHub
#: release is published -- so it is PENDING until then, and the manuscript cannot be built for
#: submission while it is.
VERSION_DOI = PENDING

CONCEPT_DOI_URL = f"https://doi.org/{CONCEPT_DOI}"
VERSION_DOI_URL = (f"https://doi.org/{VERSION_DOI}" if VERSION_DOI != PENDING
                   else "the version DOI, PENDING until the release is archived")


def is_ready() -> bool:
    """Whether the release this manuscript cites actually exists."""
    return VERSION_DOI != PENDING
