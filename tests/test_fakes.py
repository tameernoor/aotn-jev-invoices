"""FakeJev's default answers, used whenever a test doesn't care about a particular question."""

import asyncio

from fakes import FakeJev

CHOICE_QUESTIONS = {
    "document_kind": {
        "type": "choice",
        "instructions": "x",
        # "other" is a valid option but deliberately not first, to distinguish the new
        # first-option default from the old other-if-present default.
        "criteria": {"invoice": None, "reminder": None, "other": None},
    }
}

SCORE_QUESTIONS = {
    "purpose_detail": {
        "type": "score",
        "instructions": "x",
        "criteria": ["Missing or generic.", "Names the kind of work.", "Names the specific event."],
    }
}


def ask(fake: FakeJev, questions: dict):
    return asyncio.run(fake.ask({}, questions))


def test_choice_default_is_the_first_option_not_other():
    result = ask(FakeJev(), CHOICE_QUESTIONS)
    assert result.judgments["document_kind"]["value"] == "invoice"


def test_choice_explicit_value_is_still_honoured():
    result = ask(FakeJev({"document_kind": "reminder"}), CHOICE_QUESTIONS)
    assert result.judgments["document_kind"]["value"] == "reminder"


def test_score_default_is_the_top_level():
    result = ask(FakeJev(), SCORE_QUESTIONS)
    assert result.judgments["purpose_detail"]["value"] == 2.0


def test_score_explicit_value_is_still_honoured():
    result = ask(FakeJev({"purpose_detail": 1}), SCORE_QUESTIONS)
    assert result.judgments["purpose_detail"]["value"] == 1.0
