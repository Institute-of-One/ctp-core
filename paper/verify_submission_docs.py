"""Render the submission documents and check them, before anyone is asked to upload them.

    python paper/verify_submission_docs.py

Runs locally only: it drives Word to render the .docx files the portal will receive, so it needs
Windows and Word and is deliberately not in CI. Writes page images to
``paper/build/submission/pages/`` for a human to look at, because a script's pass is not a look.

Why this exists rather than the SOP checker in ~/.claude/tools: that one is written for the SOP
set -- it globs ``SOP0*.pdf``, looks for a 承認者 signature block, Japanese dates and a cover-page
company name, and diffs bold runs against an original document. None of that exists here. What
carries over is the rule behind it: a generated document is not finished until it has been
rendered and looked at, because the defects that matter -- a blank page, a legend split from its
figure, a heading alone at the foot of a page -- are invisible in the source.

What is checked automatically:

* no blank or nearly blank page
* no page whose only content is a heading (a heading orphaned from its section)
* a figure legend is not split across a page boundary
* the page count is plausible for the word count, so a document that has silently doubled or
  collapsed is caught
* the reference list is intact: numbered 1..N with nothing missing
* the manuscript carries no author name -- this journal's review is anonymous and the identity
  belongs on the title page only

Word is started with ``DispatchEx`` so it is a separate instance, and only that instance is
closed: the author usually has Word open on something else.
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BUILD = os.path.join(HERE, "build")
OUT = os.path.join(BUILD, "submission")
PAGES = os.path.join(OUT, "pages")

#: Words per page at this journal's manuscript formatting, used only to catch a document that
#: has gone badly wrong rather than to predict a layout.
WORDS_PER_PAGE = (250, 800)


def to_pdf(paths: list[str]) -> list[str]:
    """Render each .docx with Word, returning the PDFs. Word is left as it was found."""
    import win32com.client

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = False
    produced = []
    try:
        # Background pagination makes Word take twenty minutes or never finish on a document
        # with figures; without it the same export takes under a minute. Found the hard way on
        # another paper in this programme.
        try:
            word.Options.Pagination = False
        except Exception:                                    # noqa: BLE001
            pass
        for path in paths:
            pdf = os.path.splitext(path)[0] + ".pdf"
            document = word.Documents.Open(os.path.abspath(path), ReadOnly=True)
            try:
                document.SaveAs(os.path.abspath(pdf), FileFormat=17)
            finally:
                document.Close(SaveChanges=False)
            produced.append(pdf)
            print(f"  rendered {os.path.basename(pdf)}")
    finally:
        word.Quit()
    return produced


def page_text(pdf: str) -> list[str]:
    from pypdf import PdfReader

    return [(page.extract_text() or "") for page in PdfReader(pdf).pages]


def render_pages(pdf: str) -> int:
    import pypdfium2 as pdfium

    os.makedirs(PAGES, exist_ok=True)
    stem = os.path.splitext(os.path.basename(pdf))[0]
    document = pdfium.PdfDocument(pdf)
    for number, page in enumerate(document, start=1):
        image = page.render(scale=2).to_pil()
        image.save(os.path.join(PAGES, f"{stem}_p{number:02d}.png"))
    return len(document)


def check(pdf: str, words: int | None) -> list[str]:
    problems = []
    pages = page_text(pdf)
    squashed = ["".join(t.split()) for t in pages]

    for n, text in enumerate(squashed, start=1):
        if len(text) < 40:
            problems.append(f"page {n} is blank or nearly so ({len(text)} characters)")
        elif len(text) < 150 and re.match(r"^(Abstract|Introduction|Methods|Results|Discussion"
                                          r"|References|Figures|Dataavailability)", text):
            problems.append(f"page {n} holds little but a heading")

    joined = "\n".join(pages)
    for number in re.findall(r"Figure (\d+)\.", joined):
        label = f"Figure {number}."
        on = [n for n, t in enumerate(pages, start=1) if label in t]
        alt = [n for n, t in enumerate(pages, start=1)
               if f"Alt text:" in t and label in t]
        if on and not alt and any(f"Alt text:" in pages[n] for n in range(on[0], len(pages))):
            problems.append(f"the legend for figure {number} is split from its alt text "
                            f"across pages {on[0]} and {on[0] + 1}")

    if "## References" in joined or "References" in joined:
        # A surname may begin with a lowercase particle -- van Ommen, de Jong, von Neumann --
        # and requiring a capital here reported reference 3 as missing from a list that was
        # complete. The document was fine; the check was not.
        pattern = r"^(\d+)\.\s+(?:[A-Z]|van |von |de |den |der |da |du |del |di )"
        numbers = [int(n) for n in re.findall(pattern, joined, re.M)]
        if numbers:
            expected = list(range(1, max(numbers) + 1))
            missing = sorted(set(expected) - set(numbers))
            if missing:
                problems.append(f"the reference list is missing {missing}")

    if words:
        low, high = words / WORDS_PER_PAGE[1], words / WORDS_PER_PAGE[0]
        if not low - 1 <= len(pages) <= high + 4:
            problems.append(f"{len(pages)} pages for {words} words is outside the plausible "
                            f"{max(1, int(low))} to {int(high) + 4}")
    return problems


def check_anonymity(pdf: str) -> list[str]:
    import build_manuscript as build

    text = "\n".join(page_text(pdf))
    problems = []
    for identity in (build.AUTHOR, build.EMAIL, build.ORCID, "LISIT"):
        if identity and identity in text:
            problems.append(f"the manuscript names {identity!r}; it belongs on the title page")
    return problems


def main() -> int:
    targets = [os.path.join(OUT, name) for name in ("Manuscript.docx", "Title_Page.docx")]
    missing = [t for t in targets if not os.path.isfile(t)]
    if missing:
        print(f"run make_submission_files.py first: {[os.path.basename(m) for m in missing]}")
        return 1

    counts = json.loads(open(os.path.join(BUILD, "word_counts.json"), encoding="utf-8").read())
    pdfs = to_pdf(targets)

    failed = 0
    for pdf in pdfs:
        name = os.path.basename(pdf)
        words = counts["body total"] + counts["Abstract"] if "Manuscript" in name else None
        problems = check(pdf, words)
        if "Manuscript" in name:
            problems += check_anonymity(pdf)
        rendered = render_pages(pdf)
        if problems:
            failed += len(problems)
            print(f"FAIL {name} ({rendered} pages)")
            for problem in problems:
                print(f"     {problem}")
        else:
            print(f"ok   {name} ({rendered} pages)")

    print(f"\npage images in {PAGES}")
    if failed:
        print(f"{failed} problems; fix them before uploading")
        return 1
    print("The automatic checks pass. Now look at every page image: a script's pass is not a "
          "look, and the defect found by eye on the last set was one no script had.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
