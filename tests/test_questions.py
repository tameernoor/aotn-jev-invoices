import pytest
from pydantic import ValidationError

from jev_invoices.questions import QuestionCollision, QuestionSet, load_questions, merge_questions

EXPENSE_IDS = [
    "accommodation",
    "food",
    "alcohol",
    "passenger_transport",
    "customer_entertainment",
    "multiple_types",
    "category",
    "ambiguity",
]


def test_expense_questions_load_in_file_order():
    questions = load_questions("expense")
    assert list(questions) == EXPENSE_IDS
    assert questions["category"]["type"] == "choice"
    assert "other" in questions["category"]["criteria"]
    assert questions["alcohol"]["criteria"]["true"].startswith("At least one line")
    assert "criteria" not in questions["accommodation"]


def test_vendor_questions_load():
    assert list(load_questions("vendor")) == [
        "lines_describe_po",
        "bank_change_announced",
        "same_delivery_as_earlier",
    ]


def test_extra_questions_are_added_as_plain_dicts():
    extra = QuestionSet.validate_python(
        {"team_event": {"type": "noul", "instructions": "Is this a team event?"}}
    )
    merged = merge_questions(load_questions("expense"), extra)
    assert merged["team_event"] == {"type": "noul", "instructions": "Is this a team event?"}
    assert len(merged) == len(EXPENSE_IDS) + 1


def test_no_extra_questions_returns_a_copy_of_the_base():
    base = load_questions("expense")
    merged = merge_questions(base, None)
    assert merged == base
    assert merged is not base


def test_extra_question_reusing_a_builtin_id_is_rejected():
    extra = QuestionSet.validate_python(
        {"alcohol": {"type": "noul", "instructions": "Any beer?"}}
    )
    with pytest.raises(QuestionCollision, match="alcohol"):
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
