from datetime import date
from decimal import Decimal

from fakes import answers, level

from jev_invoices.questions import duplicate_question_id
from jev_invoices.rules.vendor import decide_vendor, exact_checks, recent_invoices

EARLIER = [{"invoice_number": "20877", "invoice_date": date(2026, 8, 12), "amount": Decimal("3950.00")}]


def checks(**overrides):
    args = dict(
        invoice_number="20931",
        amount=Decimal("4170.00"),
        bank_account="1503.12.34567",
        bank_account_on_file="1503.12.34567",
        po_total=Decimal("4170.00"),
        earlier_invoices=EARLIER,
    )
    return exact_checks(**{**args, **overrides})


CLEAN = dict(amount_within_tolerance=True, invoice_number_seen=False, bank_account_matches=True)


def dup(number: str, value) -> dict:
    """A judgment override for the generated duplicate question of one earlier invoice."""
    return {duplicate_question_id(number): value}


def judged(**overrides):
    base = dict(
        line_specificity=level(2),
        po_items_billed=0.95,
        unordered_items=0.05,
        bank_change_request=0.05,
        payment_pressure=0.05,
        document_kind="invoice",
    )
    return answers(**{**base, **overrides})


# --- exact_checks -----------------------------------------------------------


def test_clean_invoice_passes_every_check():
    assert checks() == CLEAN


def test_amount_given_without_decimals_equals_the_po_total():
    assert checks(amount=Decimal("4170"))["amount_within_tolerance"] is True


def test_tolerance_is_two_percent_of_the_po_total():
    assert checks(amount=Decimal("4250.00"))["amount_within_tolerance"] is True
    assert checks(amount=Decimal("4300.00"))["amount_within_tolerance"] is False


def test_bank_accounts_match_regardless_of_separators():
    assert checks(bank_account="1503 12 34567")["bank_account_matches"] is True
    assert checks(bank_account="9710.05.12345")["bank_account_matches"] is False


def test_an_empty_bank_account_does_not_match():
    assert checks(bank_account="", bank_account_on_file="")["bank_account_matches"] is False
    assert checks(bank_account="n/a", bank_account_on_file="1503.12.34567")["bank_account_matches"] is False


def test_reused_invoice_number_is_seen():
    assert checks(invoice_number="20877")["invoice_number_seen"] is True


def test_no_earlier_invoices():
    assert checks(earlier_invoices=[])["invoice_number_seen"] is False


# --- recent_invoices ----------------------------------------------------------


def test_recent_invoices_includes_the_sixtieth_day():
    earlier = [{"invoice_number": "1", "invoice_date": date(2026, 7, 14)}]
    assert recent_invoices(date(2026, 9, 12), earlier) == ["1"]


def test_recent_invoices_excludes_the_sixty_first_day():
    earlier = [{"invoice_number": "1", "invoice_date": date(2026, 7, 13)}]
    assert recent_invoices(date(2026, 9, 12), earlier) == []


# --- decide_vendor: hold -----------------------------------------------------


def test_bank_mismatch_holds_reading_nothing():
    result = decide_vendor(judged(), {**CLEAN, "bank_account_matches": False}, [])
    assert result["decision"] == "hold"
    assert result["judgments_read"] == []
    assert result["reasons"] == ["The bank account differs from the vendor record."]


def test_bank_change_request_holds():
    result = decide_vendor(judged(bank_change_request=0.95), CLEAN, [])
    assert result["decision"] == "hold"


def test_payment_pressure_holds():
    result = decide_vendor(judged(payment_pressure=0.95), CLEAN, [])
    assert result["decision"] == "hold"


# --- decide_vendor: review ----------------------------------------------------


def test_reminder_document_goes_to_review():
    result = decide_vendor(judged(document_kind="reminder"), CLEAN, [])
    assert result["decision"] == "review"
    assert result["reasons"] == ["This is not an invoice but a reminder."]


def test_credit_note_document_goes_to_review():
    result = decide_vendor(judged(document_kind="credit_note"), CLEAN, [])
    assert result["decision"] == "review"
    assert result["reasons"] == ["This is not an invoice but a credit note."]


def test_reused_invoice_number_goes_to_review():
    result = decide_vendor(judged(), {**CLEAN, "invoice_number_seen": True}, [])
    assert result["decision"] == "review"


def test_in_window_duplicate_goes_to_review_naming_the_earlier_invoice():
    result = decide_vendor(judged(**dup("20877", 0.95)), CLEAN, ["20877"])
    assert result["decision"] == "review"
    assert result["reasons"] == ["Charges for the same delivery as earlier invoice 20877."]
    assert result["duplicate_candidates"] == ["20877"]


def test_out_of_window_duplicate_is_not_read_and_invoice_approves():
    # The judgment says yes, but 20877 is not in `recent` (out of the resend window).
    result = decide_vendor(judged(**dup("20877", 0.95)), CLEAN, [])
    assert result["decision"] == "approve"
    assert "same_as_20877" not in result["judgments_read"]
    assert result["duplicate_candidates"] == []


def test_amount_outside_tolerance_goes_to_review():
    result = decide_vendor(judged(), {**CLEAN, "amount_within_tolerance": False}, [])
    assert result["decision"] == "review"


def test_specificity_level_zero_goes_to_review_without_reading_po_questions():
    result = decide_vendor(judged(line_specificity=level(0)), CLEAN, [])
    assert result["decision"] == "review"
    assert result["reasons"] == ["The invoice lines are too general to check against the purchase order."]
    assert "po_items_billed" not in result["judgments_read"]
    assert "unordered_items" not in result["judgments_read"]


def test_po_items_not_billed_goes_to_review():
    result = decide_vendor(judged(po_items_billed=0.05), CLEAN, [])
    assert result["decision"] == "review"


def test_unordered_items_goes_to_review():
    result = decide_vendor(judged(unordered_items=0.95), CLEAN, [])
    assert result["decision"] == "review"


def test_uncertain_in_window_duplicate_goes_to_review():
    result = decide_vendor(judged(**dup("20877", 0.5)), CLEAN, ["20877"])
    assert result["decision"] == "review"
    assert result["uncertain"] == ["same_as_20877"]
    assert "same_as_20877" in result["judgments_read"]
    assert result["reasons"][-1] == "Uncertain answer for: same_as_20877."


def test_out_of_window_uncertain_duplicate_is_not_read_and_invoice_approves():
    result = decide_vendor(judged(**dup("20877", 0.5)), CLEAN, [])
    assert result["decision"] == "approve"
    assert result["uncertain"] == []
    assert "same_as_20877" not in result["judgments_read"]


# --- decide_vendor: approve ---------------------------------------------------


def test_clean_invoice_is_approved():
    result = decide_vendor(judged(), CLEAN, [])
    assert result["decision"] == "approve"
    assert result["reasons"] == ["All checks passed."]
    assert result["uncertain"] == []


def test_duplicate_candidates_reports_the_recent_list_regardless_of_decision():
    result = decide_vendor(judged(**dup("20877", 0.05)), CLEAN, ["20877"])
    assert result["decision"] == "approve"
    assert result["duplicate_candidates"] == ["20877"]
