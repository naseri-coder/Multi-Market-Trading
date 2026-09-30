"""Source metadata for the Brooks Trader's Equation stage."""

from __future__ import annotations

from dataclasses import dataclass


RULE_ID = "BB-RNG-25-TRADERS-EQUATION"
SOURCE_BOOK = "TRADING_PRICE_ACTION_RANGES"
SOURCE_PDF_PAGES = (172, 173, 177)
FORMULA_VERSION = "brooks-traders-equation-v1"


@dataclass(frozen=True, slots=True)
class TraderEquationSourceEvidence:
    rule_id: str = RULE_ID
    source_book: str = SOURCE_BOOK
    source_pdf_pages: tuple[int, ...] = SOURCE_PDF_PAGES
    principle: str = (
        "A favorable trader equation requires probability-weighted reward "
        "to exceed probability-weighted risk."
    )
    probability_warning: str = (
        "Probability is uncertain and must not be represented as a calibrated "
        "crypto probability unless an upstream reviewed estimator supplies it."
    )
