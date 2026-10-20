"""The reference list, and what each citation is used to support.

Every record here was read off a live bibliographic record -- Europe PMC or Crossref -- on the
date in ``VERIFIED``, not recalled. That is not pedantry: writing this list, a DOI constructed
from a plausible pattern (``10.1088/0031-9155/37/7/004`` for Madsen 1992) resolved to a
different paper entirely, and only querying caught it. ``check_references.py`` resolves every
DOI again before the manuscript is built.

``supports`` records what each citation is cited *for*. A reference list is not a bibliography:
if a sentence claims a paper says something, that claim is checkable, and this field is where
the check starts.
"""

from __future__ import annotations

VERIFIED = "2026-10-20"

REFERENCES = {
    "vendor_disagreement": {
        "authors": "Bushnaq S, Hassan AE, Delora A, Kerro A, Datta A, Ezzeldin R, et al.",
        "title": ("A comparison of CT perfusion output of RapidAI and Viz.ai software in the "
                  "evaluation of acute ischemic stroke"),
        "journal": "AJNR Am J Neuroradiol",
        "year": 2024, "volume": "45", "issue": "7", "pages": "863-870",
        "doi": "10.3174/ajnr.a8196",
        "supports": ("Two packages given the same acquisitions return different ischemic core "
                     "volumes; the paper states that Viz.ai predicted higher core volumes than "
                     "RapidAI, over 108 adequate studies of 129 patients."),
    },
    "not_interchangeable": {
        "authors": "Fainardi E, Busto G, Morotti A",
        "title": "Automated advanced imaging in acute ischemic stroke. Certainties and uncertainties",
        "journal": "Eur J Radiol Open",
        "year": 2023, "volume": "11", "issue": "", "pages": "100524",
        "doi": "10.1016/j.ejro.2023.100524",
        "supports": ("States that automated platforms are not interchangeable because of "
                     "vendor-dependent variability."),
    },
    "harmonisation": {
        "authors": "Peerlings D, Bennink E, Dankbaar JW, Velthuis BK, de Jong HWAM",
        "title": ("Standardizing the estimation of ischemic regions can harmonize CT perfusion "
                  "stroke imaging"),
        "journal": "Eur Radiol",
        "year": 2024, "volume": "34", "issue": "2", "pages": "797-807",
        "doi": "10.1007/s00330-023-10035-1",
        "supports": ("That the disagreement between packages is addressed by standardising "
                     "processing steps, which is the motivation for attributing it to "
                     "individual steps."),
    },
    "simulation_framework": {
        "authors": "Divel SE, Christensen S, Segars WP, Lansberg MG, Pelc NJ",
        "title": "A dynamic simulation framework for CT perfusion in stroke assessment built from first principles",
        "journal": "Med Phys",
        "year": 2021, "volume": "48", "issue": "7", "pages": "3500-3510",
        "doi": "10.1002/mp.14887",
        "supports": ("The prior synthetic reference for CT perfusion, which this study does not "
                     "claim to precede. It extends the XCAT phantom and provides ground-truth "
                     "maps, and its authors name a statistical comparison of generated maps "
                     "with that truth as future work."),
    },
    "physical_phantom": {
        "authors": ("Goris LC, Zaid Al-Kaylani AHA, Schuurmann RCL, Greuter MJW, Bokkers RPH, "
                    "Manohar S"),
        "title": "Development of a cerebral CT perfusion phantom: a structured approach",
        "journal": "Phys Med",
        "year": 2025, "volume": "131", "issue": "", "pages": "104944",
        "doi": "10.1016/j.ejmp.2025.104944",
        "supports": ("That the same validation need is addressed by physical means, with "
                     "repeatability coefficients for time to peak and mean transit time below "
                     "2.3 s."),
    },
    "unitobrain": {
        "authors": ("Gava UA, D'Agata F, Tartaglione E, Renzulli R, Grangetto M, Bertolino F, "
                    "et al."),
        "title": ("Neural network-derived perfusion maps: a model-free approach to computed "
                  "tomography perfusion in patients with acute ischemic stroke"),
        "journal": "Front Neuroinform",
        "year": 2023, "volume": "17", "issue": "", "pages": "852105",
        "doi": "10.3389/fninf.2023.852105",
        "supports": ("The dataset used here, and the provenance of the maps shipped with it: "
                     "the reference maps are the output of a model-based non-linear regression "
                     "and were the training target of the network that paper presents, not the "
                     "network's output."),
    },
    "nlr_method": {
        "authors": "Bennink E, Oosterbroek J, Kudo K, Viergever MA, Velthuis BK, de Jong HWAM",
        "title": "Fast nonlinear regression method for CT brain perfusion analysis",
        "journal": "J Med Imaging (Bellingham)",
        "year": 2016, "volume": "3", "issue": "2", "pages": "026003",
        "doi": "10.1117/1.jmi.3.2.026003",
        "supports": ("The method that produced the reference maps compared against here: a "
                     "box-shaped impulse response fitted per voxel by downhill simplex. It is "
                     "a fitted method, which is why the comparison is not neutral between the "
                     "two curve models and the synthetic arm is needed."),
    },
    "prolonged_intervals": {
        "authors": "van Ommen F, Kauw F, Bennink E, Dankbaar JW, Viergever MA, de Jong HWAM",
        "title": "Effect of prolonged acquisition intervals for CT-perfusion analysis methods in patients with ischemic stroke",
        "journal": "Med Phys",
        "year": 2019, "volume": "46", "issue": "7", "pages": "3156-3164",
        "doi": "10.1002/mp.13559",
        "supports": ("The closest prior work on the sampling interval: it lengthened the "
                     "interval from 1 to 5 s on 25 patients and reported bias in CBF, CBV and "
                     "MTT and in infarct volumes, concluding that coverage can be bought by "
                     "intervals up to 5 s depending on the method. It does not examine the "
                     "time to peak, and derives no precision limit from the sampling grid."),
    },
    "ostergaard": {
        "authors": "Ostergaard L, Weisskoff RM, Chesler DA, Gyldensted C, Rosen BR",
        "title": ("High resolution measurement of cerebral blood flow using intravascular "
                  "tracer bolus passages. Part I: mathematical approach and statistical "
                  "analysis"),
        "journal": "Magn Reson Med",
        "year": 1996, "volume": "36", "issue": "5", "pages": "715-725",
        "doi": "10.1002/mrm.1910360510",
        "supports": "Singular value decomposition deconvolution, as implemented here.",
    },
    "wu_osvd": {
        "authors": "Wu O, Ostergaard L, Weisskoff RM, Benner T, Rosen BR, Sorensen AG",
        "title": ("Tracer arrival timing-insensitive technique for estimating flow in MR "
                  "perfusion-weighted imaging using singular value decomposition with a "
                  "block-circulant deconvolution matrix"),
        "journal": "Magn Reson Med",
        "year": 2003, "volume": "50", "issue": "1", "pages": "164-174",
        "doi": "10.1002/mrm.10522",
        "supports": "The block-circulant formulation this implementation uses.",
    },
    "konstas": {
        "authors": "Konstas AA, Goldmakher GV, Lee TY, Lev MH",
        "title": ("Theoretic basis and technical implementations of CT perfusion in acute "
                  "ischemic stroke, part 1: theoretic basis"),
        "journal": "AJNR Am J Neuroradiol",
        "year": 2009, "volume": "30", "issue": "4", "pages": "662-668",
        "doi": "10.3174/ajnr.a1487",
        "supports": ("The indicator-dilution formulation, including blood volume as the ratio "
                     "of the tissue and arterial areas, which is why an arterial area error "
                     "passes proportionally into it."),
    },
    "gamma_variate": {
        "authors": "Madsen MT",
        "title": "A simplified formulation of the gamma variate function",
        "journal": "Phys Med Biol",
        "year": 1992, "volume": "37", "issue": "7", "pages": "1597-1600",
        "doi": "10.1088/0031-9155/37/7/010",
        "supports": ("The gamma-variate parameterisation fitted here, whose peak time is "
                     "available in closed form from the fitted parameters -- which is why a "
                     "fitted peak can fall outside the acquisition and must be checked."),
    },
}

#: Cited by name and version rather than by DOI: a national guideline's lookup table, which has
#: no DOI. Carried separately so the DOI resolver does not have to make an exception.
NON_DOI = {
    "alut": {
        "authors": "Acute Stroke Imaging Standardization Group Japan (ASIST-Japan)",
        "title": "CT/MR perfusion imaging practical guideline 2006, standard lookup table (a-LUT)",
        "note": "Available from ASIST-Japan; the table used here is documented in A_LUT.md",
    },
}


def vancouver(key: str, number: int) -> str:
    """One reference in the Vancouver style the journal asks for."""
    if key in NON_DOI:
        r = NON_DOI[key]
        return f"{number}. {r['authors']}. {r['title']}. {r['note']}."
    r = REFERENCES[key]
    issue = f"({r['issue']})" if r["issue"] else ""
    # The author list ends with a full stop unless it already does, which it does when it ends
    # in "et al." -- without this the title runs straight on from the last author's initial.
    authors = r["authors"] if r["authors"].endswith(".") else r["authors"] + "."
    return (f"{number}. {authors} {r['title']}. {r['journal']} "
            f"{r['year']};{r['volume']}{issue}:{r['pages']}. doi:{r['doi']}")
