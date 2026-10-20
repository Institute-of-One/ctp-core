"""Assemble the files the journal's portal asks to be uploaded, as separate items.

    python paper/make_submission_files.py

Writes ``paper/build/submission/``:

* ``Manuscript.docx`` -- body, statements, figure legends with their alt text, references.
  Not the figures: the portal takes those as separate items.
* ``Title_Page.docx`` -- authors, affiliation, correspondence, competing interests, funding and
  the generative-AI statement, as a separate file because the journal asks for one.
* ``Figure_N.png`` -- each figure as its own file, at the resolution it was drawn.
* ``Alt_Text.txt`` -- the alt text for all figures in one place, since the portal asks for it
  per figure and reading it out of a .docx is error-prone.
* ``Checklist.txt`` -- what was uploaded, with the word counts and the figure resolutions, so
  the submission form can be filled in from a file rather than from memory.

Nothing here is submitted. The author uploads these.

The directory is rebuilt each time, which means it is also emptied each time -- so a file that
is in it and was not produced here stops the build rather than being deleted. On the last paper
a proof downloaded from the portal was sitting in that directory.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BUILD = os.path.join(HERE, "build")
FIGURES = os.path.join(HERE, "figures")
OUT = os.path.join(BUILD, "submission")

#: What this script writes. Anything else found in the output directory is somebody's, and is
#: not ours to delete.
PRODUCED = re.compile(r"^(Manuscript\.docx|Title_Page\.docx|Figure_\d+\.(png|pdf)"
                      r"|Alt_Text\.txt|Checklist\.txt|Manuscript\.pdf"
                      r"|Title_Page\.pdf|pages)$")


def read(name: str) -> str:
    with open(os.path.join(BUILD, name), encoding="utf-8") as handle:
        return handle.read()


def plain_headings(path: str) -> None:
    """Make the headings black.

    Pandoc's default reference document styles headings in its own blue, which is how a
    converted file looks rather than how a manuscript looks. The editorial office sees the
    upload before a reviewer does, and a document that announces its own toolchain is an
    avoidable distraction. Nothing else about the formatting is touched: the journal typesets
    its own, and a manuscript that arrives over-formatted is no better than one that arrives
    blue.
    """
    import docx
    from docx.shared import RGBColor

    document = docx.Document(path)
    for style in document.styles:
        if style.name.startswith(("Heading", "Title")):
            with contextlib.suppress(AttributeError):
                style.font.color.rgb = RGBColor(0, 0, 0)
    for paragraph in document.paragraphs:
        if paragraph.style.name.startswith(("Heading", "Title")):
            for run in paragraph.runs:
                run.font.color.rgb = RGBColor(0, 0, 0)
    document.save(path)


def prepare_output() -> list[str]:
    problems = []
    if os.path.isdir(OUT):
        foreign = [n for n in sorted(os.listdir(OUT)) if not PRODUCED.match(n)]
        if foreign:
            problems.append(
                f"{OUT} holds files this script did not write: {', '.join(foreign)}. "
                "Move them before rebuilding; they would be deleted.")
            return problems
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)
    return problems


def main() -> int:
    import pypandoc

    problems = prepare_output()
    if problems:
        for problem in problems:
            print(problem)
        return 1

    manuscript = read("manuscript.md")
    title_page = read("title_page.md")
    counts = json.loads(read("word_counts.json"))
    with open(os.path.join(FIGURES, "captions.json"), encoding="utf-8") as handle:
        figures = json.load(handle)

    pypandoc.convert_text(manuscript, "docx", format="markdown",
                          outputfile=os.path.join(OUT, "Manuscript.docx"))
    plain_headings(os.path.join(OUT, "Manuscript.docx"))
    print(f"  Manuscript.docx           ({counts['body total']} words of body, "
          f"{counts['Abstract']} of abstract)")

    pypandoc.convert_text(title_page, "docx", format="markdown",
                          outputfile=os.path.join(OUT, "Title_Page.docx"))
    plain_headings(os.path.join(OUT, "Title_Page.docx"))
    print("  Title_Page.docx           separate file, as the journal asks")

    alt_lines = []
    for number, figure in sorted(figures.items(), key=lambda kv: int(kv[0])):
        wanted = figure.get("submit", figure["file"])
        source = os.path.join(FIGURES, wanted)
        if not os.path.isfile(source):
            problems.append(f"figure {number} is in captions.json but {wanted} is "
                            "not on disk; run make_figures.py")
            continue
        suffix = os.path.splitext(wanted)[1]
        destination = os.path.join(OUT, f"Figure_{number}{suffix}")
        shutil.copyfile(source, destination)
        size = os.path.getsize(destination) / 1024
        kind = "vector" if suffix == ".pdf" else f"{figure['dpi']} dpi"
        print(f"  Figure_{number}{suffix:<5}              {kind}, {size:.0f} KB")
        alt_lines.append(f"Figure {number}\n{figure['alt_text']}\n")

    with open(os.path.join(OUT, "Alt_Text.txt"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(alt_lines))
    print(f"  Alt_Text.txt              {len(alt_lines)} figures")

    # Counted here rather than inside the f-string below, where an escaping mistake made it
    # read zero and the checklist said "References 0" while the manuscript carried thirteen.
    # A checklist that is wrong is worse than none: it is read instead of the document.
    n_references = len(re.findall(r"^\d+\.\s", manuscript.split("## References")[1], re.M))
    if n_references == 0:
        problems.append("the reference list could not be counted; the checklist would be wrong")

    checklist = [
        "What is uploaded, and what to put in the form.",
        "",
        f"Abstract      {counts['Abstract']} words (limit 250, structured, with Advances in "
        "knowledge)",
        f"Body          {counts['body total']} words (limit 3000)",
        *(f"  {name:<11} {count}" for name, count in counts.items()
          if name not in ("Abstract", "body total")),
        "",
        f"Figures       {len(alt_lines)} (limit 10), each uploaded as its own file",
        *(f"  Figure {k:<5} {'vector' if v.get('vector') else str(v['dpi']) + ' dpi'}, alt text supplied" for k, v in
          sorted(figures.items(), key=lambda kv: int(kv[0]))),
        "",
        f"References    {n_references} (limit 50), Vancouver, every DOI resolved by "
        "check_references.py",
        "Tables        0 (limit 5)",
        "",
        "Separate item: Title_Page.docx, carrying the title, article type, author and ORCID,",
        "affiliation, corresponding author, competing interests, funding, the generative-AI",
        "statement, acknowledgements and a copy of the abstract - the whole list the journal",
        "asks a title page to hold. The manuscript file carries no author identity, because",
        "the review is double-anonymised.",
        "",
        "Before uploading: run check_manuscript.py --for-submission (which also requires",
        "the version DOI to exist), check_references.py, their two proof scripts, and",
        "verify_submission_docs.py. Then look at every page image and every figure.",
    ]
    with open(os.path.join(OUT, "Checklist.txt"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(checklist) + "\n")
    print("  Checklist.txt")

    if problems:
        print()
        for problem in problems:
            print(problem)
        return 1
    print(f"\nwrote {OUT}")
    print("Nothing was submitted. These are for you to upload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
