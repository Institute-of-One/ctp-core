from __future__ import annotations

from pathlib import Path
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
IORN = Path(r"D:\DevGit\IoO\library\IORN-001")
FIG1 = IORN / "figures" / "fig1_synthetic_fit.png"
FIG2 = IORN / "figures" / "fig2_snr_sweep.png"
FIG3 = IORN / "figures" / "fig3_alut_cbf.png"
FIG4 = HERE / "figure_unitobrain_mol001.png"

BLUE = RGBColor(46, 116, 181)
DARK_BLUE = RGBColor(31, 77, 120)
MUTED = RGBColor(90, 90, 90)
BLACK = RGBColor(0, 0, 0)
LIGHT = "F4F6F9"


def set_font(run, name="Calibri", size=11, bold=None, italic=None, color=BLACK):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    run.font.size = Pt(size)
    run.font.color.rgb = color
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_cell_margins(cell, top=80, start=120, bottom=80, end=120):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = tcPr.first_child_found_in("w:tcMar")
    if tcMar is None:
        tcMar = OxmlElement("w:tcMar")
        tcPr.append(tcMar)
    for m, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tcMar.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            tcMar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_repeat_table_header(row):
    trPr = row._tr.get_or_add_trPr()
    tblHeader = OxmlElement("w:tblHeader")
    tblHeader.set(qn("w:val"), "true")
    trPr.append(tblHeader)


def set_fixed_table(table, widths_inches):
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    total = int(round(sum(widths_inches) * 1440))
    tblPr = table._tbl.tblPr
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:w"), str(total))
    tblW.set(qn("w:type"), "dxa")
    tblInd = tblPr.find(qn("w:tblInd"))
    if tblInd is None:
        tblInd = OxmlElement("w:tblInd")
        tblPr.append(tblInd)
    tblInd.set(qn("w:w"), "120")
    tblInd.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths_inches:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(int(round(width * 1440))))
        grid.append(col)
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            dxa = int(round(widths_inches[idx] * 1440))
            cell.width = Inches(widths_inches[idx])
            tcW = cell._tc.get_or_add_tcPr().find(qn("w:tcW"))
            if tcW is None:
                tcW = OxmlElement("w:tcW")
                cell._tc.get_or_add_tcPr().append(tcW)
            tcW.set(qn("w:w"), str(dxa))
            tcW.set(qn("w:type"), "dxa")
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)


def configure_document(doc: Document, manuscript=True):
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal.font.size = Pt(11)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6 if not manuscript else 8)
    normal.paragraph_format.line_spacing = 1.1 if not manuscript else 1.25
    for name, size, color, before, after in (
        ("Heading 1", 16, BLUE, 16, 8),
        ("Heading 2", 13, BLUE, 12, 6),
        ("Heading 3", 12, DARK_BLUE, 8, 4),
    ):
        style = styles[name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        style.font.size = Pt(size)
        style.font.color.rgb = color
        style.font.bold = True
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_font(header.add_run("SoftwareX | Original Software Publication" if manuscript else "Cover letter"), size=8.5, color=MUTED)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    footer._p.append(fld)


def add_title_block(doc):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    set_font(p.add_run("ctp-core: An open and reproducible Python core for gamma-variate CT-perfusion analysis and standardized visualization"), size=18, bold=True, color=DARK_BLUE)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(3)
    set_font(p.add_run("Shuji Yamamoto, PhD"), size=11.5, bold=True)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    set_font(p.add_run("Institute of One, LISIT Co., Ltd., Tokyo 150-0044, Japan"), size=10.5)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(12)
    set_font(p.add_run("Corresponding author: yamamoto@lisit.jp | ORCID: 0000-0001-9211-1071"), size=9.5, color=MUTED)


def add_heading(doc, text, level=1):
    return doc.add_paragraph(text, style=f"Heading {level}")


def add_body(doc, text, italic=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_font(p.add_run(text), italic=italic)
    return p


def add_figure(doc, path, width, caption):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    shape = p.add_run().add_picture(str(path), width=Inches(width))
    shape._inline.docPr.set("descr", caption)
    shape._inline.docPr.set("title", path.stem)
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_before = Pt(3)
    cap.paragraph_format.space_after = Pt(8)
    set_font(cap.add_run(caption), size=9, italic=True, color=MUTED)


def add_spec_table(doc):
    # Rows C1-C8 and the three column headings are fixed by the SoftwareX Original
    # Software Publication template (softwarex-osp-template.docx). The left column is to
    # be left untouched. C2 must be the GitHub repository: the template states that a
    # GitHub repository is mandatory and that the paper will not proceed without one, so
    # the Zenodo archive is cited in the availability statement and reference [8] instead.
    rows = [
        ("C1", "Current code version", "v0.1.1"),
        ("C2", "Permanent link to code/repository used for this code version", "https://github.com/Institute-of-One/ctp-core/tree/v0.1.1"),
        ("C3", "Legal code license", "MIT"),
        ("C4", "Code versioning system used", "Git"),
        ("C5", "Software code languages, tools and services used", "Python >=3.9; NumPy; SciPy; Matplotlib; Git; GitHub; GitHub Actions; Zenodo"),
        ("C6", "Compilation requirements, operating environments and dependencies", "Pure Python package requiring no compilation; NumPy, SciPy and Matplotlib only; CPU execution; platform-independent; no graphical-user-interface or DICOM dependency"),
        ("C7", "If available, link to developer documentation/manual", "https://github.com/Institute-of-One/ctp-core/blob/v0.1.1/README.md"),
        ("C8", "Support email for questions", "yamamoto@lisit.jp"),
    ]
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    hdr = table.rows[0]
    set_repeat_table_header(hdr)
    for idx, txt in enumerate(("Nr", "Code metadata description", "Metadata")):
        shade(hdr.cells[idx], "E8EEF5")
        set_font(hdr.cells[idx].paragraphs[0].add_run(txt), size=9, bold=True)
    for a, b, c in rows:
        cells = table.add_row().cells
        for idx, txt in enumerate((a, b, c)):
            set_font(cells[idx].paragraphs[0].add_run(txt), size=8.7)
    set_fixed_table(table, [0.45, 2.35, 3.70])


def make_manuscript():
    doc = Document()
    configure_document(doc, manuscript=True)
    add_title_block(doc)

    add_heading(doc, "Abstract", 1)
    add_body(doc, "Quantitative CT-perfusion (CTP) analysis is sensitive to post-processing choices, yet research implementations are often difficult to audit or reproduce. ctp-core is a small, open Python library exposing the numerical core of a CTP workflow without a graphical user interface, DICOM input/output, or patient data: baseline correction and smoothing, gamma-variate fitting of first-pass curves, analytic peak, time-to-peak, bolus-arrival-time and area-under-the-curve indices, voxel-wise maps, arterial-input-function ranking, block-circulant singular-value-decomposition utilities, and value-preserving visualization with the ASIST-Japan lookup table. Fits report explicit failure messages rather than unusable estimates. Over 200 seeded realizations at each of five signal-to-noise ratios (SNRs), mean absolute peak-time error fell from 0.518 s at SNR 5 to 0.025 s at SNR 100, and peak-amplitude relative error from 8.08% to 0.41%. The software, tests, examples and versioned archive are public under the MIT license. ctp-core is an auditable research reference, not a clinically validated diagnostic product.")
    p = doc.add_paragraph()
    set_font(p.add_run("Keywords: "), bold=True)
    # The template allows a maximum of six. "perfusion imaging" was the seventh and is
    # subsumed by "CT perfusion".
    set_font(p.add_run("CT perfusion; gamma-variate; research software; reproducibility; standardized visualization; ASIST-Japan"))

    add_heading(doc, "Code metadata", 1)
    add_spec_table(doc)

    add_heading(doc, "1. Motivation and significance", 1)
    add_body(doc, "CTP converts temporally sampled contrast enhancement into curves and parametric images used in stroke and other perfusion applications. The outputs depend on preprocessing, arterial-input-function selection, mathematical modeling, regularization, and display choices. Delay sensitivity and implementation details can materially affect derived maps [1-4]. Commercial packages are clinically useful but generally do not expose every numerical decision. Open implementations therefore serve a distinct research need: they allow investigators to audit assumptions, reproduce intermediate values, test sensitivity, and separate numerical values from visualization.")
    add_body(doc, "Gamma-variate models have long been used to represent first-pass indicator-dilution curves [5,6]; ctp-core does not claim that model as a new theory. Its contribution is a compact, dependency-light and testable implementation in which derived indices are calculated analytically from fitted parameters, error states are explicit, synthetic ground truth is generated reproducibly, and the ASIST-Japan a-LUT is packaged as a deterministic visualization resource. This scope differs from comprehensive end-to-end applications such as PyPeT, which processes raw CTP and MR-perfusion data and has been compared with commercial map outputs [7]. ctp-core is deliberately narrower: it is a reusable numerical reference component that excludes DICOM workflow and the private interactive application. The boundary reduces deployment complexity and permits independent inspection without exposing patient or client data.")
    add_body(doc, "The software is useful for method developers who need transparent curve fitting, educators demonstrating first-pass models, researchers constructing sensitivity experiments, and groups wishing to standardize the display of quantitative perfusion maps while retaining their underlying voxel values. A versioned Zenodo archive [8] and a citable medRxiv preprint [9] preserve the exact public release used here.")

    add_heading(doc, "2. Software description", 1)
    add_heading(doc, "2.1 Software architecture", 2)
    add_body(doc, "ctp-core is organized into seven modules. synthetic generates deterministic time-attenuation curves with configurable amplitude, onset, shape, scale, sampling, SNR, recirculation, and random seed. gamma_fit implements the gamma-variate model, initialization, bounded nonlinear least-squares fitting, raw indices, analytic fit-derived indices, and voxel-wise maps. preprocessing provides baseline estimation and optional temporal smoothing. tdc_analysis supplies curve extraction and summary operations. aif_detection screens and ranks arterial candidates and can group spatial candidates. parametric_maps contains block-circulant SVD deconvolution and CBF, CBV, MTT, TTP, and Tmax map utilities. a_lut loads the packaged ASIST-Japan table, maps scalars to indices, and exports RGB images and color bars.")
    add_body(doc, "The public library depends only on NumPy, SciPy, and Matplotlib. It neither reads DICOM nor makes clinical decisions. The private application is a separate consumer of the core. This one-way dependency prevents duplication of the numerical logic and makes the open release independently importable.")

    add_heading(doc, "2.2 Software functionalities", 2)
    add_body(doc, "For time t after bolus onset t0, the model is C(t) = K(t-t0)^alpha exp[-(t-t0)/beta], with C(t)=0 at or before t0. Evaluation uses logarithmic arithmetic where appropriate for numerical stability. Fitting uses scipy.optimize.curve_fit with physically constrained parameters and a data-driven initial estimate. The fitted parameters directly give peak time t_peak=t0+alpha beta, peak value K(alpha beta)^alpha exp(-alpha), and AUC=K beta^(alpha+1) Gamma(alpha+1). BAT is t0. This avoids a second optimization for derived quantities.")
    add_body(doc, "Every call returns a GammaFitResult containing success, fitted parameters, derived indices, RMSE, R-squared, and error_message. Invalid shape, too few samples, non-finite input, absent bolus, optimizer failure, or non-finite output is therefore visible to downstream code. A fit-free path is also provided: raw TTP is the sampled maximum time, peak is the sampled maximum, AUC is the trapezoidal integral of the positive enhancement, and BAT is the first rising-limb sample above 10% of peak.")

    add_body(doc, "The mapping utilities include arterial candidate screening, ranking by bolus-shape features, and block-circulant truncated-SVD deconvolution. These functions are exposed for research use, but the present software paper does not claim clinical accuracy for CBF, CBV, MTT, or lesion classification. Their theoretical basis and sensitivity to delay and regularization are documented in the literature [1-4].")
    add_body(doc, "The packaged a-LUT maps normalized scalar values to one of 256 RGB entries and supports documented display ranges. The transformation is visualization-only: quantitative arrays remain unchanged. Deterministic tests verify LUT loading, scalar-to-index behavior, and exact RGB output. Standardizing display cannot remove algorithmic differences, but it prevents arbitrary colormap choice from becoming an additional source of visual inconsistency.")

    add_heading(doc, "3. Illustrative examples", 1)
    add_body(doc, "Every example below is reproducible from the archived release after installing requirements-core.txt. Section 3.1 is regenerated by python examples/run_synthetic_demo.py and Section 3.2 by python examples/run_snr_sweep.py; each writes both its figure and a JSON record of the values quoted here. Section 3.3 is regenerated by make_a_lut_figures.py. The test suite runs with python -m pytest tests -q. Fixed seeds make the synthetic examples deterministic within a compatible numerical environment.")
    add_heading(doc, "3.1 Reproducible single-curve fit", 2)
    add_body(doc, "The first example generates 40 samples at 1-s spacing from a curve with peak enhancement 60 HU, t0=8 s, alpha=3, beta=2, SNR=20, and seed 0. The analytic peak time is 14 s. The fitted curve produced peak time 14.140 s, peak enhancement 57.543 HU, BAT 8.210 s, R-squared 0.988, and RMSE 2.077 HU. The example writes both a figure and a JSON record containing the configuration, ground truth, raw indices, fitted values, and errors.")
    add_figure(doc, FIG1, 5.9, "Fig. 1. Deterministic synthetic first-pass curve, noisy observation (SNR 20), and ctp-core gamma-variate fit. Source: examples/run_synthetic_demo.py, seed 0.")

    add_heading(doc, "3.2 Monte-Carlo recovery across SNR", 2)
    add_body(doc, "The second example repeats the fit for seeds 0-199 at SNR 5, 10, 20, 40, and 100. Of 1,000 attempted fits, 999 passed; the failed SNR-5 fit was excluded explicitly. Mean absolute peak-time error decreased monotonically from 0.518 to 0.025 s, while mean peak-amplitude relative error decreased from 8.08% to 0.41%. At SNR 20, all 200 fits succeeded; mean absolute peak-time error was 0.128 s, peak-amplitude relative error was 2.03%, BAT error was 0.513 s, and mean R-squared was 0.980. These results validate recovery for the stated synthetic model and sampling design; they do not establish performance for all bolus geometries or clinical acquisitions.")
    add_figure(doc, FIG2, 6.1, "Fig. 2. Recovery error and fit quality across five SNR levels. Error bars are mean +/- standard deviation over 200 seeded realizations per level.")

    add_heading(doc, "3.3 Standardized map rendering", 2)
    add_body(doc, "The visualization example renders the same deterministic synthetic CBF array in grayscale and with the ASIST-Japan a-LUT over a 0-80 mL/100 g/min window. The low-CBF center is more readily distinguished in the standardized color presentation, while the numerical array is preserved exactly.")
    add_figure(doc, FIG3, 5.7, "Fig. 3. Identical synthetic CBF values rendered in grayscale and with the ASIST-Japan a-LUT. Color mapping does not alter quantitative values.")

    add_heading(doc, "3.4 End-to-end illustration on public CTP data", 2)
    add_body(doc, "To demonstrate execution on an independently sourced acquisition, the public UniToBrain v1.4 test case MOL-001 [11] was converted from DICOM to a 4D array by an external loader and passed to ctp-core. The loaded series comprised 18 time points, 16 axial slices, and 512 x 512 pixels over 47.77 s. On axial slice 8, automated arterial screening selected 17 voxels; the resulting enhancement curve reached 106.9 HU and its gamma-variate fit had R-squared 0.894. Block-circulant SVD with a 0.15 truncation threshold produced the illustrative CBF, CBV, MTT, and TTP maps in Fig. 4. These outputs establish technical interoperability and successful execution on public clinical images, not diagnostic accuracy or agreement with a reference package. Fig. 4 and its provenance JSON are regenerated by submission/softwarex/make_unitobrain_figure.py after obtaining UniToBrain case MOL-001 separately and installing pydicom together with a JPEG Lossless decoder.")
    add_figure(doc, FIG4, 6.15, "Fig. 4. Illustrative ctp-core execution on public UniToBrain v1.4 test case MOL-001. (A) Baseline CT and automatically detected AIF location; (B) detected arterial enhancement and gamma-variate fit; (C-F) CBF, CBV, MTT, and TTP maps from block-circulant SVD. Dataset DOI: 10.5281/zenodo.5109415. Maps are research outputs and have not been clinically validated.")

    add_heading(doc, "4. Impact", 1)
    add_body(doc, "ctp-core turns an otherwise application-bound analysis implementation into a small, citable and inspectable research object. The practical impact is not a claim of superior clinical map accuracy. It is the availability of traceable numerical operations, stable example outputs, explicit failure handling, and a standardized display implementation that can be reused independently. The generated JSON artifacts make numerical claims machine-checkable. The public test suite covers imports, dependency boundaries, curve generation, noiseless and noisy recovery, raw indices, failure behavior, AIF handling, and deterministic LUT output. Continuous integration runs the suite and both examples on supported Python versions.")
    add_body(doc, "The architecture also provides a clean extension point. Alternative fit models, initialization schemes, regularization thresholds, AIF ranking criteria, or display standards can be evaluated without coupling experiments to a GUI or DICOM loader. Because the reference generator has known parameters, regressions can be distinguished from changes in observational data. The repository can therefore support reproducibility studies, teaching, and unit-level verification within larger perfusion pipelines.")

    add_heading(doc, "5. Conclusions", 1)
    add_body(doc, "ctp-core exposes the numerical core of a CT-perfusion workflow as a small, auditable and citable Python library: deterministic curve generation, gamma-variate fitting with indices derived analytically from the fitted parameters, explicit failure states in place of silent propagation, arterial-input-function and block-circulant deconvolution utilities, and value-preserving rendering with the ASIST-Japan standardized lookup table. Against known synthetic ground truth, mean absolute peak-time error fell from 0.518 s at SNR 5 to 0.025 s at SNR 100 and mean peak-amplitude relative error from 8.08% to 0.41%, and the library ran end to end on an independently released public CTP case. Because the numerical logic is separated from any graphical interface or DICOM loader, it can be inspected, tested and reused on its own.")
    add_body(doc, "The reported validation is synthetic and centered on one gamma-variate geometry across five SNR levels. The public-data example demonstrates execution only: it does not measure diagnostic performance, agreement with reference maps, inter-vendor agreement, infarct-core segmentation, or absolute flow accuracy. The arterial-input-function and deconvolution modules are implemented but not externally validated in this release, and the library does not ingest DICOM, perform registration, or supply a clinical interface. It is research software and must not be used as a medical device.")
    add_body(doc, "Planned work is broader factorial simulation over temporal sampling, bolus shape, delay, truncation, and recirculation; public-data validation of the parametric maps; comparison against independent reference implementations; distribution through a standard Python index; and community-contributed tests. These extensions should remain separated from clinical claims unless supported by appropriate data, reference standards, and governance.")

    add_heading(doc, "Declarations", 1)
    add_heading(doc, "Ethics statement", 2)
    add_body(doc, "The software development and synthetic experiments did not involve new recruitment or intervention. The illustrative clinical image is from the openly released, de-identified UniToBrain dataset [11]. The source study reports institutional review-board approval (Comitato Etico Interaziendale, CEI, id 596.345), compliance with the Declaration of Helsinki, and waiver of written informed consent because of its retrospective design. No attempt was made to identify any participant.")
    add_heading(doc, "Data and software availability", 2)
    add_body(doc, "Synthetic data reported in this paper are generated by the public software. The public clinical example is UniToBrain v1.4, test case MOL-001: https://doi.org/10.5281/zenodo.5109415. Source code: https://github.com/Institute-of-One/ctp-core. Archived release (v0.1.1, the version described here): https://doi.org/10.5281/zenodo.22226447. Concept DOI: https://doi.org/10.5281/zenodo.20921268. Software license: MIT.")
    add_heading(doc, "Funding", 2)
    add_body(doc, "This research received no specific grant from funding agencies in the public, commercial, or not-for-profit sectors.")
    add_heading(doc, "Declaration of competing interest", 2)
    add_body(doc, "The author declares that he has no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.")
    add_heading(doc, "CRediT authorship contribution statement", 2)
    add_body(doc, "Shuji Yamamoto: Conceptualization, Methodology, Software, Validation, Formal analysis, Investigation, Data curation, Visualization, Writing - original draft, Writing - review & editing, Project administration.")
    add_heading(doc, "Declaration of generative AI and AI-assisted technologies", 2)
    add_body(doc, "During preparation of the software and manuscript, the author used AI assistants for code scaffolding and review, test drafting, release preparation, figure-script assistance, and language editing. The author reviewed, edited, and independently re-executed the reported numerical analyses and takes full responsibility for the content. No AI system is an author.")

    add_heading(doc, "References", 1)
    refs = [
        "[1] Fieselmann A, Kowarschik M, Ganguly A, Hornegger J, Fahrig R. Deconvolution-based CT and MR brain perfusion measurement: theoretical model revisited and practical implementation details. Int J Biomed Imaging. 2011;2011:467563. https://doi.org/10.1155/2011/467563.",
        "[2] Wu O, Ostergaard L, Weisskoff RM, Benner T, Rosen BR, Sorensen AG. Tracer arrival timing-insensitive technique for estimating flow in MR perfusion-weighted imaging using singular value decomposition with a block-circulant deconvolution matrix. Magn Reson Med. 2003;50:164-174. https://doi.org/10.1002/mrm.10522.",
        "[3] Kudo K, Sasaki M, Ogasawara K, Terae S, Ehara S, Shirato H. Difference in tracer delay-induced effect among deconvolution algorithms in CT perfusion analysis: quantitative evaluation with digital phantoms. Radiology. 2009;251:241-249. https://doi.org/10.1148/radiol.2511080983.",
        "[4] Konstas AA, Goldmakher GV, Lee TY, Lev MH. Theoretic basis and technical implementations of CT perfusion in acute ischemic stroke, part 1: theoretic basis. AJNR Am J Neuroradiol. 2009;30:662-668. https://doi.org/10.3174/ajnr.A1487.",
        "[5] Madsen MT. A simplified formulation of the gamma variate function. Phys Med Biol. 1992;37:1597-1600. https://doi.org/10.1088/0031-9155/37/7/010.",
        "[6] Thompson HK Jr, Starmer CF, Whalen RE, McIntosh HD. Indicator transit time considered as a gamma variate. Circ Res. 1964;14:502-515. https://doi.org/10.1161/01.RES.14.6.502.",
        "[7] Borghouts M, Su R. PyPeT: A Python Perfusion Tool for Automated Quantitative Brain CT and MR Perfusion Analysis. arXiv:2511.13310; 2025. https://doi.org/10.48550/arXiv.2511.13310.",
        "[8] Yamamoto S. ctp-core: Open, reproducible CT Perfusion analysis core (IORN-001), version v0.1.1. Zenodo; 2026. https://doi.org/10.5281/zenodo.22226447.",
        "[9] Yamamoto S. An Open, Reproducible Gamma-Variate Pipeline for CT-Perfusion Time-Attenuation Curve Analysis, with Standardized (ASIST-Japan) Map Visualization. medRxiv; 2026. https://doi.org/10.64898/2026.06.26.26356666.",
        "[10] Acute Stroke Imaging Standardization Group Japan. CT/MR Perfusion Imaging Practical Guideline 2006 and standard perfusion color scale (a-LUT). https://asist.umin.jp/ (accessed 24 August 2026).",
        "[11] Gava U, D'Agata F, Bennink E, et al. UniToBrain Dataset (v1.4). Zenodo; 2021. https://doi.org/10.5281/zenodo.5109415. See also: Gava U, D'Agata F, Tartaglione E, et al. Neural network-derived perfusion maps: a model-free approach to computed tomography perfusion in patients with acute ischemic stroke. Front Neuroinform. 2023;17:852105. https://doi.org/10.3389/fninf.2023.852105.",
    ]
    for ref in refs:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.25)
        p.paragraph_format.first_line_indent = Inches(-0.25)
        p.paragraph_format.space_after = Pt(4)
        set_font(p.add_run(ref), size=9.5)

    out = HERE / "ctp-core_SoftwareX_manuscript.docx"
    doc.save(out)
    return out


def make_cover_letter():
    doc = Document()
    configure_document(doc, manuscript=False)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(4)
    set_font(p.add_run("COVER LETTER"), size=20, bold=True, color=DARK_BLUE)
    p = doc.add_paragraph()
    set_font(p.add_run("SoftwareX - Original Software Publication"), size=12, bold=True, color=MUTED)

    for line in ("24 August 2026", "Editors-in-Chief", "SoftwareX"):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        set_font(p.add_run(line))

    add_body(doc, "Dear Editors-in-Chief,")
    add_body(doc, "Please consider the manuscript entitled 'ctp-core: An open and reproducible Python core for gamma-variate CT-perfusion analysis and standardized visualization' for publication as an Original Software Publication in SoftwareX.")
    add_body(doc, "ctp-core is a publicly released, MIT-licensed research library that separates auditable CT-perfusion numerical methods from a private graphical and DICOM workflow. It provides gamma-variate fitting, analytic derivation of Peak, TTP, BAT, and AUC, explicit failure reporting, deterministic synthetic benchmarks, arterial-input-function and deconvolution utilities, and value-preserving visualization using the ASIST-Japan standardized lookup table. The manuscript is intentionally precise about scope: it presents a reusable and reproducible software component, not a clinically validated diagnostic product.")
    add_body(doc, "The submission fits SoftwareX because the principal contribution is open research software with demonstrated scientific relevance and reuse potential. The repository includes source code, documentation, examples, a synthetic-data generator, a test suite, continuous integration, citation metadata, and a versioned Zenodo archive. Quantitative recovery is evaluated with deterministic synthetic data, and end-to-end execution is additionally illustrated using the independently released UniToBrain public CTP dataset. The exact software release described in the manuscript is archived at https://doi.org/10.5281/zenodo.22226447.")
    add_body(doc, "A prior version of the scientific description is publicly available as a medRxiv preprint (https://doi.org/10.64898/2026.06.26.26356666). The manuscript is not under consideration by another journal and has not been published as a peer-reviewed journal article. No human or animal subjects and no patient or client data were used. The author declares no competing interests and no specific external funding.")
    add_body(doc, "AI assistants were used as disclosed in the manuscript for code and manuscript support. I independently reviewed the work, re-executed the numerical analyses, and take full responsibility for the submission.")
    add_body(doc, "Thank you for considering this submission. I would be pleased to respond to editorial or reviewer questions and to make reasonable improvements to the public software during review.")
    add_body(doc, "Sincerely,")
    p = doc.add_paragraph()
    set_font(p.add_run("Shuji Yamamoto, PhD"), bold=True)
    for line in ("Institute of One, LISIT Co., Ltd., Tokyo 150-0044, Japan", "Email: yamamoto@lisit.jp", "ORCID: 0000-0001-9211-1071"):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        set_font(p.add_run(line))
    out = HERE / "ctp-core_SoftwareX_cover_letter.docx"
    doc.save(out)
    return out


if __name__ == "__main__":
    for required in (FIG1, FIG2, FIG3):
        if not required.exists():
            raise FileNotFoundError(required)
    print(make_manuscript())
    print(make_cover_letter())
