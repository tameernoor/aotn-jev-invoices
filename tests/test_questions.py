import pytest
from pydantic import ValidationError

from jev_invoices.questions import (
    QuestionCollision,
    QuestionSet,
    duplicate_question_id,
    duplicate_questions,
    load_questions,
    merge_questions,
    vendor_request_questions,
)

EXPENSE_IDS = [
    "lodging_charged",
    "served_food_charged",
    "alcohol_charged",
    "transport_charged",
    "goods_charged",
    "hosted_guests",
    "guests_named",
    "purpose_fits_receipt",
    "personal_items",
    "receipt_kind",
    "purpose_detail",
]

VENDOR_IDS = [
    "line_specificity",
    "po_items_billed",
    "unordered_items",
    "bank_change_request",
    "payment_pressure",
    "document_kind",
]


def test_expense_questions_load_in_file_order():
    questions = load_questions("expense")
    assert list(questions) == EXPENSE_IDS
    assert questions["receipt_kind"]["type"] == "choice"
    assert "other" in questions["receipt_kind"]["criteria"]
    assert questions["alcohol_charged"]["criteria"]["true"].startswith("At least one line")
    assert set(questions["lodging_charged"]["criteria"]) == {"true", "false"}
    assert questions["purpose_detail"]["type"] == "score"
    assert len(questions["purpose_detail"]["criteria"]) == 3


def test_vendor_questions_load():
    assert list(load_questions("vendor")) == VENDOR_IDS
    questions = load_questions("vendor")
    assert questions["document_kind"]["type"] == "choice"
    assert questions["line_specificity"]["type"] == "score"


def test_extra_questions_are_added_as_plain_dicts():
    extra = QuestionSet.validate_python(
        {"team_event": {"type": "noul", "instructions": "Is this a team event?"}}
    )
    merged = merge_questions(load_questions("expense"), extra)
    assert merged["team_event"] == {"type": "noul", "instructions": "Is this a team event?"}
    assert len(merged) == len(EXPENSE_IDS) + 1


def test_extra_questions_accept_unvalidated_plain_dicts():
    extra = {"team_event": {"type": "noul", "instructions": "Is this a team event?"}}
    merged = merge_questions(load_questions("expense"), extra)
    assert merged["team_event"] == {"type": "noul", "instructions": "Is this a team event?"}


def test_no_extra_questions_returns_a_copy_of_the_base():
    base = load_questions("expense")
    merged = merge_questions(base, None)
    assert merged == base
    assert merged is not base


def test_extra_question_reusing_a_builtin_id_is_rejected():
    extra = QuestionSet.validate_python(
        {"alcohol_charged": {"type": "noul", "instructions": "Any beer?"}}
    )
    with pytest.raises(QuestionCollision, match="alcohol_charged"):
        merge_questions(load_questions("expense"), extra)


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "score", "instructions": "x", "criteria": ["only one level"]},
        {"type": "score", "instructions": "x", "criteria": [str(i) for i in range(11)]},
        {"type": "choice", "instructions": "x", "criteria": {f"o{i}": None for i in range(256)}},
        {"type": "choice", "instructions": "x", "criteria": {"only": None}},
        {"type": "bogus", "instructions": "x"},
        {"type": "noul"},
    ],
)
def test_malformed_questions_are_rejected(bad):
    with pytest.raises(ValidationError):
        QuestionSet.validate_python({"q": bad})


def test_duplicate_question_id_sanitises_the_invoice_number():
    assert duplicate_question_id("INV-2026/07") == "same_as_INV_2026_07"


def test_duplicate_question_id_strips_leading_and_trailing_junk():
    assert duplicate_question_id("-20877-") == "same_as_20877"


def test_duplicate_questions_shape_and_validity():
    earlier = [{"invoice_number": "20877", "text": "Kaffebønner, hele, 1 kg"}]
    questions = duplicate_questions(earlier)
    assert list(questions) == ["same_as_20877"]
    question = questions["same_as_20877"]
    assert question["type"] == "noul"
    assert question["instructions"]["earlier_invoice"] == {
        "invoice_number": "20877",
        "text": "Kaffebønner, hele, 1 kg",
    }
    assert "question" in question["instructions"]
    assert set(question["criteria"]) == {"true", "false"}
    # Validates as a real question set.
    QuestionSet.validate_python(questions)


def test_duplicate_questions_one_per_earlier_invoice():
    earlier = [
        {"invoice_number": "20877", "text": "a"},
        {"invoice_number": "20931", "text": "b"},
    ]
    assert list(duplicate_questions(earlier)) == ["same_as_20877", "same_as_20931"]


def test_duplicate_questions_raises_on_colliding_sanitised_ids():
    earlier = [{"invoice_number": "INV-1", "text": "a"}, {"invoice_number": "INV/1", "text": "b"}]
    with pytest.raises(QuestionCollision, match="same_as_INV_1"):
        duplicate_questions(earlier)


def test_duplicate_questions_raises_on_empty_sanitised_id():
    earlier = [{"invoice_number": "///", "text": "a"}]
    with pytest.raises(QuestionCollision, match="same_as_"):
        duplicate_questions(earlier)


def test_duplicate_questions_do_not_share_the_same_criteria_object():
    earlier = [
        {"invoice_number": "20877", "text": "a"},
        {"invoice_number": "20931", "text": "b"},
    ]
    questions = duplicate_questions(earlier)
    first = questions["same_as_20877"]["criteria"]
    second = questions["same_as_20931"]["criteria"]
    assert first == second
    assert first is not second


def test_vendor_request_questions_with_no_earlier_invoices_equals_the_base():
    base = load_questions("vendor")
    assert vendor_request_questions(base, []) == base


def test_vendor_request_questions_adds_one_duplicate_question_per_earlier_invoice():
    base = load_questions("vendor")
    earlier = [{"invoice_number": "20877", "text": "a"}]
    merged = vendor_request_questions(base, earlier)
    assert set(merged) == set(base) | {"same_as_20877"}
