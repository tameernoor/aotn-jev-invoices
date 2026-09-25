from datetime import date
from decimal import Decimal

from fakes import answers

from jev_invoices.rules.vendor import decide_vendor, exact_checks

EARLIER = [{"invoice_number": "20877", "invoice_date": date(2026, 8, 12), "amount": Decimal("3950.00")}]


def checks(**overrides):
    args = dict(
        invoice_number="20931",
        amount=Decimal("4170.00"),
        invoice_date=date(2026, 9, 12),
        bank_account="1503.12.34567",
        bank_account_on_file="1503.12.34567",
        po_total=Decimal("4170.00"),
        earlier_invoices=EARLIER,
    )
    return exact_checks(**{**args, **overrides})


CLEAN = dict(amount_within_tolerance=True, invoice_number_seen=False, bank_account_matches=True, same_amount_as_earlier=False)


def judged(**overrides):
    return answers(**{**dict(lines_describe_po=0.95, bank_change_announced=0.05, same_delivery_as_earlier=0.05), **overrides})


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


def test_same_amount_counts_only_within_sixty_days():
    earlier = [{"invoice_number": "1", "invoice_date": date(2026, 7, 14), "amount": Decimal("4170")}]
    assert checks(earlier_invoices=earlier)["same_amount_as_earlier"] is True
    earlier[0]["invoice_date"] = date(2026, 7, 13)
    assert checks(earlier_invoices=earlier)["same_amount_as_earlier"] is False


def test_no_earlier_invoices():
    result = checks(earlier_invoices=[])
    assert result["invoice_number_seen"] is False
    assert result["same_amount_as_earlier"] is False


def test_clean_invoice_is_approved_without_reading_the_duplicate_question():
    result = decide_vendor(judged(), CLEAN)
    assert result["decision"] == "approve"
    assert "same_delivery_as_earlier" not in result["judgments_read"]


def test_bank_mismatch_holds_without_asking_jev_anything():
    result = decide_vendor(judged(), {**CLEAN, "bank_account_matches": False})
    assert result["decision"] == "hold"
    assert result["judgments_read"] == []


def test_bank_change_announced_in_text_holds():
    result = decide_vendor(judged(bank_change_announced=0.95), CLEAN)
    assert result["decision"] == "hold"


def test_reused_invoice_number_goes_to_review():
    assert decide_vendor(judged(), {**CLEAN, "invoice_number_seen": True})["decision"] == "review"


def test_same_amount_and_same_delivery_goes_to_review():
    result = decide_vendor(judged(same_delivery_as_earlier=0.95), {**CLEAN, "same_amount_as_earlier": True})
    assert result["decision"] == "review"


def test_same_amount_but_different_delivery_is_approved():
    result = decide_vendor(judged(), {**CLEAN, "same_amount_as_earlier": True})
    assert result["decision"] == "approve"


def test_amount_outside_tolerance_goes_to_review():
    assert decide_vendor(judged(), {**CLEAN, "amount_within_tolerance": False})["decision"] == "review"


def test_lines_that_do_not_describe_the_po_go_to_review():
    assert decide_vendor(judged(lines_describe_po=0.05), CLEAN)["decision"] == "review"


def test_uncertain_answer_goes_to_review():
    result = decide_vendor(judged(lines_describe_po=0.5), CLEAN)
    assert result["decision"] == "review"
    assert result["uncertain"] == ["lines_describe_po"]
