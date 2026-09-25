"""Illustrative Norwegian VAT coding for employee expenses. Not tax advice.

Codes are Skatteetaten's SAF-T standard tax codes (Standard_Tax_Codes.csv).
Rates from skatteetaten.no/satser/merverdiavgift (2026): regular 25 %, food 15 %,
passenger transport and room rental 12 %. No deduction for serving (servering)
or entertainment (representasjon), merverdiavgiftsloven § 8-3 (1) a and e.
"""

import re

from .judgments import Judgments

NO_VAT_TREATMENT = "0"  # Ingen merverdiavgiftsbehandling (anskaffelser)
DEDUCTIBLE_REGULAR_RATE = "1"  # Fradragsberettiget innenlands inngående mva, regular rate
DEDUCTIBLE_LOW_RATE = "13"  # Fradragsberettiget innenlands inngående mva, reduced rate, low

_VAT_WORD = re.compile(r"\b(mva|moms|vat)\b", re.IGNORECASE)
_PERCENT = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s?%")


def vat_rates_found(text: str) -> list[str]:
    """Percentages on lines that mention VAT. Counting is a job for code, not Jev."""
    rates = set()
    for line in text.splitlines():
        if _VAT_WORD.search(line):
            rates.update(match.replace(",", ".") for match in _PERCENT.findall(line))
    return sorted(rates, key=float)


ACCEPTED_DOCUMENTS = {"proof_of_purchase"}
GENERIC_PURPOSE_BELOW = 0.5  # purpose_detail level 0


def apply_tax_rules(judgments: dict, *, invoice_text: str, employee_country: str, vendor_country: str) -> dict:
    j = Judgments(judgments)
    reasons: list[str] = []
    flags: list[str] = []
    foreign_purchase = employee_country.upper() != vendor_country.upper()
    kinds: list[str] = []
    should_split = False
    saft_code = None

    guests = j.hosted_guests
    if foreign_purchase:
        saft_code = NO_VAT_TREATMENT
        reasons.append("Foreign vendor: foreign VAT is not Norwegian input VAT, no deduction.")
    else:
        if j.lodging_charged:
            kinds.append("lodging")
        if j.served_food_charged or j.alcohol_charged:
            kinds.append("food_and_drink")
        if j.transport_charged:
            kinds.append("transport")
        if j.goods_charged:
            kinds.append("goods")

        if len(kinds) > 1:
            should_split = True
            reasons.append("Several kinds of expense on one invoice: split it into lines before coding.")
        elif not kinds:
            flags.append("Could not tell what was bought, so no VAT code was chosen.")
        elif kinds == ["food_and_drink"]:
            saft_code = NO_VAT_TREATMENT
            if guests:
                reasons.append("Customer entertainment (representasjon): no deduction, § 8-3 (1) e.")
            else:
                reasons.append("Food or drinks served (servering): no deduction, § 8-3 (1) a.")
        elif kinds[0] in ("lodging", "transport"):
            saft_code = DEDUCTIBLE_LOW_RATE
            reasons.append("Accommodation or passenger transport: deductible at the low rate (12 %).")
        else:
            saft_code = DEDUCTIBLE_REGULAR_RATE
            reasons.append("Goods: deductible at the regular rate (25 %).")

    document = j.choice("receipt_kind")
    if document not in ACCEPTED_DOCUMENTS:
        flags.append(f"Not valid documentation: {document.replace('_', ' ')}.")
    if j.no("purpose_fits_receipt"):
        flags.append("What was bought does not fit the stated purpose.")
    if j.personal_items:
        flags.append("The receipt includes at least one item for private use.")
    if guests and not j.guests_named:
        flags.append("Customer entertainment must name the guests or their company.")
    if j.score("purpose_detail") < GENERIC_PURPOSE_BELOW:
        flags.append("The purpose is missing or too generic.")

    if j.uncertain:
        flags.append(f"Uncertain answer for: {', '.join(j.uncertain)}.")

    return {
        "saft_code": saft_code,
        "should_split": should_split,
        "foreign_purchase": foreign_purchase,
        "kinds": kinds,
        "vat_rates_found": vat_rates_found(invoice_text),
        "needs_review": bool(flags),
        "flags": flags,
        "judgments_read": list(j.read),
        "uncertain": list(j.uncertain),
        "reasons": reasons,
    }
