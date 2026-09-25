from fakes import answers, level

from jev_invoices.rules.expense import apply_tax_rules, vat_rates_found

BASE = dict(
    lodging_charged=0.05,
    served_food_charged=0.05,
    alcohol_charged=0.05,
    transport_charged=0.05,
    goods_charged=0.05,
    hosted_guests=0.05,
    guests_named=0.05,
    purpose_fits_receipt=0.95,
    personal_items=0.05,
    receipt_kind="proof_of_purchase",
    purpose_detail=level(1),
)


def judged(**overrides):
    return answers(**{**BASE, **overrides})


def code(judgments, employee="NO", vendor="NO", text="MVA 25 %"):
    return apply_tax_rules(judgments, invoice_text=text, employee_country=employee, vendor_country=vendor)


def test_domestic_hotel_only_is_low_rate():
    result = code(judged(lodging_charged=0.95))
    assert result["saft_code"] == "13"
    assert result["kinds"] == ["lodging"]
    assert result["needs_review"] is False


def test_hotel_and_minibar_food_splits_two_kinds():
    result = code(judged(lodging_charged=0.95, alcohol_charged=0.95))
    assert result["should_split"] is True
    assert result["kinds"] == ["lodging", "food_and_drink"]
    assert result["saft_code"] is None
    assert result["needs_review"] is False


def test_alcohol_is_read_before_served_food_and_short_circuits():
    result = code(judged(alcohol_charged=0.95, served_food_charged=0.5))
    assert result["kinds"] == ["food_and_drink"]
    assert "served_food_charged" not in result["judgments_read"]
    assert result["needs_review"] is False


def test_dinner_with_named_guests_is_no_deduction_entertainment():
    result = code(judged(served_food_charged=0.95, hosted_guests=0.95, guests_named=0.95))
    assert result["saft_code"] == "0"
    assert any("§ 8-3 (1) e" in reason for reason in result["reasons"])
    assert result["flags"] == []
    assert result["needs_review"] is False


def test_dinner_with_guests_not_named_flags():
    result = code(judged(served_food_charged=0.95, hosted_guests=0.95, guests_named=0.05))
    assert result["saft_code"] == "0"
    assert any("must name the guests" in flag for flag in result["flags"])
    assert result["needs_review"] is True


def test_guests_named_not_read_when_hosted_guests_is_no():
    result = code(judged(served_food_charged=0.95, guests_named=0.5))
    assert "guests_named" not in result["judgments_read"]
    assert result["needs_review"] is False


def test_meal_without_guests_is_servering_no_deduction():
    result = code(judged(served_food_charged=0.95))
    assert result["saft_code"] == "0"
    assert any("§ 8-3 (1) a" in reason for reason in result["reasons"])


def test_goods_only_is_regular_rate():
    result = code(judged(goods_charged=0.95))
    assert result["saft_code"] == "1"
    assert result["kinds"] == ["goods"]


def test_no_kinds_leaves_code_unset_and_flags():
    result = code(judged())
    assert result["saft_code"] is None
    assert result["kinds"] == []
    assert any("Could not tell what was bought" in flag for flag in result["flags"])
    assert result["needs_review"] is True


def test_card_slip_is_not_valid_documentation():
    result = code(judged(goods_charged=0.95, receipt_kind="card_slip"))
    assert any("Not valid documentation" in flag for flag in result["flags"])
    assert result["needs_review"] is True


def test_booking_confirmation_is_not_valid_documentation():
    result = code(judged(goods_charged=0.95, receipt_kind="booking_confirmation"))
    assert any("Not valid documentation" in flag for flag in result["flags"])


def test_proof_of_purchase_is_accepted_documentation():
    result = code(judged(transport_charged=0.95, receipt_kind="proof_of_purchase"))
    assert not any("Not valid documentation" in flag for flag in result["flags"])


def test_purpose_not_fitting_receipt_flags():
    result = code(judged(goods_charged=0.95, purpose_fits_receipt=0.05))
    assert any("does not fit the stated purpose" in flag for flag in result["flags"])


def test_personal_item_flags():
    result = code(judged(goods_charged=0.95, personal_items=0.95))
    assert any("item for private use" in flag for flag in result["flags"])


def test_generic_purpose_detail_flags():
    result = code(judged(goods_charged=0.95, purpose_detail=level(0)))
    assert any("missing or too generic" in flag for flag in result["flags"])


def test_low_confidence_receipt_kind_is_uncertain_and_reviewed():
    low_confidence = {
        "type": "choice",
        "value": "proof_of_purchase",
        "probabilities": {"proof_of_purchase": 0.5},
        "confidence": 0.5,
    }
    result = code(judged(goods_charged=0.95, receipt_kind=low_confidence))
    assert result["uncertain"] == ["receipt_kind"]
    assert result["needs_review"] is True
    assert any("Uncertain answer for" in flag for flag in result["flags"])


def test_foreign_reads_none_of_the_kind_judgments():
    result = code(judged(lodging_charged=0.5), vendor="SE")
    kind_ids = {"lodging_charged", "served_food_charged", "alcohol_charged", "transport_charged", "goods_charged"}
    assert result["foreign_purchase"] is True
    assert result["saft_code"] == "0"
    assert kind_ids.isdisjoint(result["judgments_read"])
    assert result["needs_review"] is False


def test_country_codes_are_case_insensitive():
    result = code(judged(lodging_charged=0.95), employee="no", vendor="No")
    assert result["foreign_purchase"] is False
    assert result["saft_code"] == "13"


def test_vat_rates_come_only_from_vat_lines():
    text = "Rabatt 10 %\nSum 2 989,00\nHerav mva 12 %  310,71\nHerav MVA 25 %  17,80\nTips 5 %"
    assert vat_rates_found(text) == ["12", "25"]


def test_vat_rates_read_swedish_and_english_and_decimals():
    assert vat_rates_found("Varav moms 12 %") == ["12"]
    assert vat_rates_found("of which VAT 12.5%") == ["12.5"]
    assert vat_rates_found("Ingen mva her") == []
