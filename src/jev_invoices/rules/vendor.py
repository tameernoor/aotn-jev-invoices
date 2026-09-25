"""Vendor invoice approval. Code compares numbers, dates and accounts; Jev reads descriptions.

The duplicate check only looks at the earlier invoices sent with the request, not the store.
"""

from datetime import date
from decimal import Decimal

from .judgments import Judgments

TOLERANCE = Decimal("0.02")  # invoice may differ from the PO total by 2 %
RESEND_WINDOW_DAYS = 60


def _digits(account: str) -> str:
    return "".join(ch for ch in account if ch.isdigit())


def exact_checks(
    *,
    invoice_number: str,
    amount: Decimal,
    invoice_date: date,
    bank_account: str,
    bank_account_on_file: str,
    po_total: Decimal,
    earlier_invoices: list[dict],
) -> dict[str, bool]:
    return {
        "amount_within_tolerance": abs(amount - po_total) <= po_total * TOLERANCE,
        "invoice_number_seen": any(e["invoice_number"] == invoice_number for e in earlier_invoices),
        "bank_account_matches": bool(_digits(bank_account))
        and bool(_digits(bank_account_on_file))
        and _digits(bank_account) == _digits(bank_account_on_file),
        "same_amount_as_earlier": any(
            e["amount"] == amount and abs((invoice_date - e["invoice_date"]).days) <= RESEND_WINDOW_DAYS
            for e in earlier_invoices
        ),
    }


def decide_vendor(judgments: dict, checks: dict[str, bool]) -> dict:
    j = Judgments(judgments)
    reasons: list[str] = []

    if not checks["bank_account_matches"]:
        decision = "hold"
        reasons.append("The bank account differs from the vendor record.")
    elif j.bank_change_announced:
        decision = "hold"
        reasons.append("The invoice text announces a new or changed bank account.")
    elif checks["invoice_number_seen"]:
        decision = "review"
        reasons.append("The invoice number was already used by an earlier invoice.")
    elif checks["same_amount_as_earlier"] and j.same_delivery_as_earlier:
        decision = "review"
        reasons.append("Same amount and same delivery as an earlier invoice, probably sent twice.")
    elif not checks["amount_within_tolerance"]:
        decision = "review"
        reasons.append("The amount differs from the purchase order total by more than 2 %.")
    elif j.no("lines_describe_po"):
        decision = "review"
        reasons.append("The invoice lines do not describe what the purchase order ordered.")
    elif j.uncertain:
        decision = "review"
    else:
        decision = "approve"
        reasons.append("All checks passed.")

    if j.uncertain:
        reasons.append(f"Uncertain answer for: {', '.join(j.uncertain)}.")

    return {
        "decision": decision,
        "checks": checks,
        "judgments_read": list(j.read),
        "uncertain": list(j.uncertain),
        "reasons": reasons,
    }
