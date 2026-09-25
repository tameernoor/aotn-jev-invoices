from fakes import answers

from jev_invoices.rules.expense import apply_tax_rules, vat_rates_found

BASE = dict(
    accommodation=0.05,
    food=0.05,
    alcohol=0.05,
    passenger_transport=0.05,
    customer_entertainment=0.05,
    multiple_types=0.05,
    category="other",
)


def judged(**overrides):
    return answers(**{**BASE, **overrides})


def code(judgments, employee="NO", vendor="NO", text="MVA 25 %"):
    return apply_tax_rules(judgments, invoice_text=text, employee_country=employee, vendor_country=vendor)


def test_domestic_hotel_is_low_rate_and_ignores_unread_uncertain_answers():
    result = code(judged(accommodation=0.95, passenger_transport=0.5, category="accommodation"))
    assert result["saft_code"] == "13"
    assert result["category_check"] == "agrees"
    assert "passenger_transport" not in result["judgments_read"]
    assert result["uncertain"] == []
    assert result["needs_review"] is False


def test_hotel_with_minibar_beer_is_split_before_coding():
    result = code(judged(accommodation=0.95, alcohol=0.95, multiple_types=0.95, category="accommodation"))
    assert result["should_split"] is True
    assert result["saft_code"] is None
    assert result["category_check"] == "not_checked"
    assert result["needs_review"] is False


def test_customer_dinner_gets_no_deduction():
    result = code(judged(food=0.95, alcohol=0.95, customer_entertainment=0.95, category="entertainment"))
    assert result["saft_code"] == "0"
    assert any("§ 8-3 (1) e" in reason for reason in result["reasons"])
    assert result["category_check"] == "agrees"


def test_meal_without_guests_gets_no_deduction():
    result = code(judged(food=0.95, category="food"))
    assert result["saft_code"] == "0"
    assert any("§ 8-3 (1) a" in reason for reason in result["reasons"])


def test_foreign_vendor_reads_no_judgments_at_all():
    everything_uncertain = {qid: 0.5 for qid in BASE if qid != "category"}
    result = code(judged(**everything_uncertain), vendor="SE")
    assert result["foreign_purchase"] is True
    assert result["saft_code"] == "0"
    assert result["judgments_read"] == []
    assert result["needs_review"] is False


def test_country_codes_are_case_insensitive():
    result = code(judged(passenger_transport=0.95, category="passenger_transport"), employee="no", vendor="No")
    assert result["foreign_purchase"] is False
    assert result["saft_code"] == "13"


def test_uncertain_answer_the_rules_read_triggers_review():
    result = code(judged(multiple_types=0.5, passenger_transport=0.95, category="passenger_transport"))
    assert result["uncertain"] == ["multiple_types"]
    assert result["needs_review"] is True


def test_category_that_contradicts_the_nouls_triggers_review():
    result = code(judged(passenger_transport=0.95, category="food"))
    assert result["saft_code"] == "13"
    assert result["category_check"] == "disagrees"
    assert result["needs_review"] is True


def test_other_category_agrees_only_with_the_regular_rate():
    assert code(judged())["saft_code"] == "1"
    assert code(judged())["category_check"] == "agrees"
    taxi_called_other = code(judged(passenger_transport=0.95, category="other"))
    assert taxi_called_other["category_check"] == "disagrees"


def test_vat_rates_come_only_from_vat_lines():
    text = "Rabatt 10 %\nSum 2 989,00\nHerav mva 12 %  310,71\nHerav MVA 25 %  17,80\nTips 5 %"
    assert vat_rates_found(text) == ["12", "25"]


def test_vat_rates_read_swedish_and_english_and_decimals():
    assert vat_rates_found("Varav moms 12 %") == ["12"]
    assert vat_rates_found("of which VAT 12.5%") == ["12.5"]
    assert vat_rates_found("Ingen mva her") == []
