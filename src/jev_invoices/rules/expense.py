"""Illustrative Norwegian VAT coding for employee expenses. Not tax advice.

Codes are Skatteetaten's SAF-T standard tax codes (Standard_Tax_Codes.csv).
Rates from skatteetaten.no/satser/merverdiavgift (2026): regular 25 %, food 15 %,
passenger transport and room rental 12 %. No deduction for serving (servering)
or entertainment (representasjon), merverdiavgiftsloven § 8-3 (1) a and e.
"""

import re
from decimal import Decimal

from ..questions import line_question_id
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
GENERIC_PURPOSE_BELOW = 0.5

LINE_CODES = {
    "lodging": (DEDUCTIBLE_LOW_RATE, "Accommodation: deductible at the low rate (12 %)."),
    "transport": (DEDUCTIBLE_LOW_RATE, "Passenger transport: deductible at the low rate (12 %)."),
    "served_food": (NO_VAT_TREATMENT, "Served food (servering): no deduction, § 8-3 (1) a."),
    "alcohol": (NO_VAT_TREATMENT, "Alcohol: no deduction, § 8-3 (1) a, and never the food rate, § 5-2 (3)."),
    "goods": (DEDUCTIBLE_REGULAR_RATE, "Goods for work: deductible at the regular rate (25 %)."),
}


def apply_tax_rules(judgments, *, lines, invoice_text, employee_country, vendor_country) -> dict:
    j = Judgments(judgments)
    reasons: list[str] = []
    flags: list[str] = []
    foreign_purchase = employee_country.upper() != vendor_country.upper()

    coded = []
    for i, line in enumerate(lines):
        category = j.choice(line_question_id(i))
        if foreign_purchase:
            code = NO_VAT_TREATMENT
        elif category in LINE_CODES:
            code, reason = LINE_CODES[category]
            if reason not in reasons:
                reasons.append(reason)
        else:
            code = None
        if category == "private_item":
            flags.append(f"Private item: {line['text']}.")
        elif category == "other_cost":
            reasons.append(f"No VAT code in this example for: {line['text']}. Code it by hand.")
        elif category == "unclear":
            flags.append(f"Could not tell what was bought: {line['text']}.")
        coded.append({"text": line["text"], "amount": line["amount"], "category": category, "saft_code": code})

    if foreign_purchase:
        reasons.append("Foreign vendor: foreign VAT is not Norwegian input VAT, no deduction.")
    if not lines:
        flags.append("The receipt lists nothing that was bought.")

    totals: dict[str, Decimal] = {}
    for line in coded:
        if line["saft_code"] is not None:
            totals[line["saft_code"]] = totals.get(line["saft_code"], Decimal("0")) + line["amount"]

    document = j.choice("receipt_kind")
    if document not in ACCEPTED_DOCUMENTS:
        flags.append(f"Not valid documentation: {document.replace('_', ' ')}.")
    if j.no("purpose_fits_receipt"):
        flags.append("What was bought does not fit the stated purpose.")
    if any(line["category"] in ("served_food", "alcohol") for line in coded) and j.food_for_several:
        if not j.diners_named:
            flags.append("Hospitality must say who ate or drank (bokføringsforskriften § 5-10).")
    if j.score("purpose_detail") < GENERIC_PURPOSE_BELOW:
        flags.append("The purpose is missing or too generic.")
    if j.uncertain:
        flags.append(f"Uncertain answer for: {', '.join(j.uncertain)}.")

    return {
        "foreign_purchase": foreign_purchase,
        "lines": coded,
        "totals_by_code": totals,
        "vat_rates_found": vat_rates_found(invoice_text),
        "needs_review": bool(flags),
        "flags": flags,
        "judgments_read": list(j.read),
        "uncertain": list(j.uncertain),
        "reasons": reasons,
    }
