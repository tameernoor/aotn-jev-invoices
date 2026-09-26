from decimal import Decimal

from fakes import answers, level

from jev_invoices.questions import line_question_id
from jev_invoices.rules.expense import apply_tax_rules, vat_rates_found

BASE = dict(
    hosted_guests=0.05,
    guests_named=0.05,
    purpose_fits_receipt=0.95,
    receipt_kind="proof_of_purchase",
    purpose_detail=level(1),
)


def receipt_lines(rows: list[tuple[str, str, str]]) -> tuple[list[dict], dict[str, str]]:
    """[(text, amount, category), ...] -> (lines for the rules, line_N judgments)."""
    lines = []
    categories = {}
    for i, (text, amount, category) in enumerate(rows):
        lines.append({"text": text, "amount": Decimal(amount)})
        categories[line_question_id(i)] = category
    return lines, categories


def code(rows=(), employee="NO", vendor="NO", text="MVA 25 %", **overrides):
    lines, categories = receipt_lines(list(rows))
    judgments = answers(**{**BASE, **categories, **overrides})
    return apply_tax_rules(judgments, lines=lines, invoice_text=text, employee_country=employee, vendor_country=vendor)


def test_hotel_and_minibar_beer_are_coded_and_totalled():
    result = code(
        [
            ("Overnatting enkeltrom, 2 netter", "2900.00", "lodging"),
            ("Minibar: Pils 0,33 l", "89.00", "alcohol"),
        ]
    )
    assert [line["saft_code"] for line in result["lines"]] == ["13", "0"]
    assert result["totals_by_code"] == {"13": Decimal("2900.00"), "0": Decimal("89.00")}
    assert result["needs_review"] is False


def test_dinner_with_named_guests_is_entertainment_and_flag_free():
    result = code(
        [
            ("Hovedrett torsk", "1185.00", "served_food"),
            ("Flaske hvitvin, Chablis", "890.00", "alcohol"),
            ("Kaffe", "135.00", "served_food"),
        ],
        hosted_guests=0.95,
        guests_named=0.95,
    )
    assert [line["saft_code"] for line in result["lines"]] == ["0", "0", "0"]
    assert any("§ 8-3 (1) e" in reason for reason in result["reasons"])
    assert any("§ 5-2 (3)" in reason for reason in result["reasons"])
    assert result["flags"] == []
    assert result["needs_review"] is False


def test_dinner_with_guests_not_named_flags():
    result = code(
        [
            ("Hovedrett torsk", "1185.00", "served_food"),
            ("Flaske hvitvin, Chablis", "890.00", "alcohol"),
        ],
        hosted_guests=0.95,
        guests_named=0.05,
    )
    assert any("must name the guests" in flag for flag in result["flags"])
    assert result["needs_review"] is True


def test_alcohol_reason_mentions_5_2_3_regardless_of_guests():
    result = code([("Pils", "89.00", "alcohol")])
    assert result["lines"][0]["saft_code"] == "0"
    assert any("§ 5-2 (3)" in reason for reason in result["reasons"])


def test_meal_without_guests_is_servering_no_deduction():
    result = code([("Lunsj", "150.00", "served_food")])
    assert result["lines"][0]["saft_code"] == "0"
    assert any("§ 8-3 (1) a" in reason for reason in result["reasons"])


def test_goods_are_regular_rate():
    result = code([("USB-C-lader 65 W", "598.00", "goods")])
    assert result["lines"][0]["saft_code"] == "1"
    assert result["totals_by_code"] == {"1": Decimal("598.00")}


def test_private_item_is_uncoded_and_flags_the_line():
    result = code([("Leppepomade", "49.00", "private_item")])
    assert result["lines"][0]["saft_code"] is None
    assert any("Leppepomade" in flag for flag in result["flags"])
    assert result["needs_review"] is True
    assert result["totals_by_code"] == {}


def test_other_cost_tip_is_uncoded_with_a_reason_and_no_flag():
    result = code([("Driks", "50.00", "other_cost")])
    assert result["lines"][0]["saft_code"] is None
    assert any("Driks" in reason for reason in result["reasons"])
    assert result["flags"] == []
    assert result["needs_review"] is False


def test_unclear_line_flags():
    result = code([("???", "10.00", "unclear")])
    assert any("Could not tell what was bought" in flag for flag in result["flags"])
    assert result["needs_review"] is True


def test_no_lines_flags():
    result = code([])
    assert result["lines"] == []
    assert result["totals_by_code"] == {}
    assert any("nothing that was bought" in flag for flag in result["flags"])
    assert result["needs_review"] is True


def test_foreign_purchase_codes_everything_zero_but_still_flags_private_item():
    result = code(
        [
            ("Rum, 1 natt", "1690.00", "lodging"),
            ("Leppepomade", "49.00", "private_item"),
        ],
        vendor="SE",
    )
    assert result["foreign_purchase"] is True
    assert [line["saft_code"] for line in result["lines"]] == ["0", "0"]
    assert any("Leppepomade" in flag for flag in result["flags"])
    assert any("Foreign vendor" in reason for reason in result["reasons"])


def test_low_confidence_line_choice_is_uncertain_and_reviewed():
    low_confidence = {
        "type": "choice",
        "value": "goods",
        "probabilities": {"goods": 0.5},
        "confidence": 0.5,
    }
    result = code([("Ukjent vare", "20.00", "goods")], line_1=low_confidence)
    assert result["uncertain"] == ["line_1"]
    assert result["needs_review"] is True
    assert any("Uncertain answer for" in flag for flag in result["flags"])


def test_card_slip_is_not_valid_documentation():
    result = code([("USB-C-lader", "598.00", "goods")], receipt_kind="card_slip")
    assert any("Not valid documentation" in flag for flag in result["flags"])
    assert result["needs_review"] is True


def test_booking_confirmation_is_not_valid_documentation():
    result = code([("Item", "10.00", "goods")], receipt_kind="booking_confirmation")
    assert any("Not valid documentation" in flag for flag in result["flags"])


def test_proof_of_purchase_is_accepted_documentation():
    result = code([("Tur", "845.00", "transport")], receipt_kind="proof_of_purchase")
    assert not any("Not valid documentation" in flag for flag in result["flags"])


def test_purpose_not_fitting_receipt_flags():
    result = code([("Item", "10.00", "goods")], purpose_fits_receipt=0.05)
    assert any("does not fit the stated purpose" in flag for flag in result["flags"])


def test_generic_purpose_detail_flags():
    result = code([("Item", "10.00", "goods")], purpose_detail=level(0))
    assert any("missing or too generic" in flag for flag in result["flags"])


def test_guests_named_not_read_when_hosted_guests_is_no():
    result = code([("Lunsj", "150.00", "served_food")], guests_named=0.5)
    assert "guests_named" not in result["judgments_read"]
    assert result["needs_review"] is False


def test_country_codes_are_case_insensitive():
    result = code([("Rum, 1 natt", "1690.00", "lodging")], employee="no", vendor="No")
    assert result["foreign_purchase"] is False
    assert result["lines"][0]["saft_code"] == "13"


def test_vat_rates_come_only_from_vat_lines():
    text = "Rabatt 10 %\nSum 2 989,00\nHerav mva 12 %  310,71\nHerav MVA 25 %  17,80\nTips 5 %"
    assert vat_rates_found(text) == ["12", "25"]


def test_vat_rates_read_swedish_and_english_and_decimals():
    assert vat_rates_found("Varav moms 12 %") == ["12"]
    assert vat_rates_found("of which VAT 12.5%") == ["12.5"]
    assert vat_rates_found("Ingen mva her") == []
