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

# The yes/no question that should agree with each main category.
CATEGORY_TO_JUDGMENT = {
    "accommodation": "accommodation",
    "food": "food",
    "alcohol": "alcohol",
    "passenger_transport": "passenger_transport",
    "entertainment": "customer_entertainment",
}

_VAT_WORD = re.compile(r"\b(mva|moms|vat)\b", re.IGNORECASE)
_PERCENT = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s?%")


def vat_rates_found(text: str) -> list[str]:
    """Percentages on lines that mention VAT. Counting is a job for code, not Jev."""
    rates = set()
    for line in text.splitlines():
        if _VAT_WORD.search(line):
            rates.update(match.replace(",", ".") for match in _PERCENT.findall(line))
    return sorted(rates, key=float)


def apply_tax_rules(judgments: dict, *, invoice_text: str, employee_country: str, vendor_country: str) -> dict:
    j = Judgments(judgments)
    reasons: list[str] = []
    foreign_purchase = employee_country.upper() != vendor_country.upper()
    should_split = False
    saft_code = None

    if foreign_purchase:
        saft_code = NO_VAT_TREATMENT
        reasons.append("Foreign vendor: foreign VAT is not Norwegian input VAT, no deduction.")
    elif j.multiple_types:
        should_split = True
        reasons.append("Several kinds of expense on one invoice: split it into lines before coding.")
    elif j.customer_entertainment:
        saft_code = NO_VAT_TREATMENT
        reasons.append("Customer entertainment (representasjon): no deduction, § 8-3 (1) e.")
    elif j.food or j.alcohol:
        saft_code = NO_VAT_TREATMENT
        reasons.append("Food or drinks served (servering): no deduction, § 8-3 (1) a.")
    elif j.accommodation or j.passenger_transport:
        saft_code = DEDUCTIBLE_LOW_RATE
        reasons.append("Accommodation or passenger transport: deductible at the low rate (12 %).")
    else:
        saft_code = DEDUCTIBLE_REGULAR_RATE
        reasons.append("Other purchase: deductible at the regular rate (25 %).")

    category_check = "not_checked"
    if saft_code is not None and not foreign_purchase:
        category = j.choice("category")
        if category == "other":
            agrees = saft_code == DEDUCTIBLE_REGULAR_RATE
        else:
            agrees = not j.no(CATEGORY_TO_JUDGMENT[category])
        category_check = "agrees" if agrees else "disagrees"
        if not agrees:
            reasons.append(f"Main category '{category}' disagrees with the yes/no answers.")

    if j.uncertain:
        reasons.append(f"Uncertain answer for: {', '.join(j.uncertain)}.")

    return {
        "saft_code": saft_code,
        "category_check": category_check,
        "should_split": should_split,
        "foreign_purchase": foreign_purchase,
        "vat_rates_found": vat_rates_found(invoice_text),
        "needs_review": bool(j.uncertain) or category_check == "disagrees",
        "judgments_read": list(j.read),
        "uncertain": list(j.uncertain),
        "reasons": reasons,
    }
