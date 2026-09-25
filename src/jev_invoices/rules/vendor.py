"""Vendor invoice approval. Code compares numbers, dates and accounts; Jev reads descriptions.

Duplicate suspicion is answered per earlier invoice, one generated question per invoice
within the resend window (see questions.duplicate_questions).
"""

from datetime import date
from decimal import Decimal

from ..questions import duplicate_question_id
from .judgments import Judgments

TOLERANCE = Decimal("0.02")  # invoice may differ from the PO total by 2 %
RESEND_WINDOW_DAYS = 60
SPECIFIC_LINES_FROM = 0.5  # line_specificity level 0 is generic


def _digits(account: str) -> str:
    return "".join(ch for ch in account if ch.isdigit())


def exact_checks(*, invoice_number, amount, bank_account, bank_account_on_file, po_total, earlier_invoices) -> dict[str, bool]:
    return {
        "amount_within_tolerance": abs(amount - po_total) <= po_total * TOLERANCE,
        "invoice_number_seen": any(e["invoice_number"] == invoice_number for e in earlier_invoices),
        "bank_account_matches": bool(_digits(bank_account))
        and bool(_digits(bank_account_on_file))
        and _digits(bank_account) == _digits(bank_account_on_file),
    }


def recent_invoices(invoice_date: date, earlier_invoices: list[dict]) -> list[str]:
    """Earlier invoice numbers dated within the resend window. Date arithmetic stays in code."""
    return [
        e["invoice_number"]
        for e in earlier_invoices
        if abs((invoice_date - e["invoice_date"]).days) <= RESEND_WINDOW_DAYS
    ]


def decide_vendor(judgments: dict, checks: dict[str, bool], recent: list[str]) -> dict:
    j = Judgments(judgments)
    reasons: list[str] = []

    if not checks["bank_account_matches"]:
        decision = "hold"
        reasons.append("The bank account differs from the vendor record.")
    elif j.bank_change_request:
        decision = "hold"
        reasons.append("The invoice asks for payment to a new or changed bank account.")
    elif j.payment_pressure:
        decision = "hold"
        reasons.append("The invoice pushes for immediate payment or for skipping approval.")
    elif (document := j.choice("document_kind")) != "invoice":
        decision = "review"
        reasons.append(f"This is not an invoice but a {document.replace('_', ' ')}.")
    elif checks["invoice_number_seen"]:
        decision = "review"
        reasons.append("The invoice number was already used by an earlier invoice.")
    elif duplicates := [n for n in recent if j.yes(duplicate_question_id(n))]:
        decision = "review"
        reasons.append(f"Charges for the same delivery as earlier invoice {', '.join(duplicates)}.")
    elif not checks["amount_within_tolerance"]:
        decision = "review"
        reasons.append("The amount differs from the purchase order total by more than 2 %.")
    elif j.score("line_specificity") < SPECIFIC_LINES_FROM:
        decision = "review"
        reasons.append("The invoice lines are too general to check against the purchase order.")
    elif j.no("po_items_billed"):
        decision = "review"
        reasons.append("The invoice lines do not describe what the purchase order ordered.")
    elif j.unordered_items:
        decision = "review"
        reasons.append("The invoice charges for something the purchase order does not include.")
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
        "duplicate_candidates": list(recent),
        "judgments_read": list(j.read),
        "uncertain": list(j.uncertain),
        "reasons": reasons,
    }
