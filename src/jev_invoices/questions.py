"""Question sets. The YAML files define the classifiers; requests can add more."""

import re
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, TypeAdapter

QUESTIONS_DIR = Path(__file__).resolve().parents[2] / "questions"

Content = str | dict | list


class NoulQuestion(BaseModel):
    type: Literal["noul"]
    instructions: Content
    criteria: dict[Literal["true", "false"], Content] | None = None


class ChoiceQuestion(BaseModel):
    type: Literal["choice"]
    instructions: Content
    criteria: dict[str, Content | None] = Field(min_length=2, max_length=255)


class ScoreQuestion(BaseModel):
    type: Literal["score"]
    instructions: Content
    criteria: list[Content] = Field(min_length=2, max_length=10)


Question = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]
QuestionSet = TypeAdapter(dict[str, Question])


class QuestionCollision(ValueError):
    """An extra question reuses the id of a built-in question."""


def _as_dicts(questions: dict) -> dict[str, dict]:
    return {
        qid: question.model_dump(exclude_none=True) if hasattr(question, "model_dump") else question
        for qid, question in questions.items()
    }


def load_questions(kind: str, directory: Path = QUESTIONS_DIR) -> dict[str, dict]:
    raw = yaml.safe_load((directory / f"{kind}.yaml").read_text(encoding="utf-8"))
    return _as_dicts(QuestionSet.validate_python(raw))


def merge_questions(base: dict[str, dict], extra: dict | None) -> dict[str, dict]:
    if not extra:
        return dict(base)
    clash = sorted(set(base) & set(extra))
    if clash:
        raise QuestionCollision(f"extra_questions reuse built-in ids: {', '.join(clash)}")
    return {**base, **_as_dicts(extra)}


LINE_QUESTION = "What kind of purchase is `line`?"
LINE_CRITERIA = {
    "lodging": "One or more nights of accommodation, such as a hotel room. A room with breakfast on one line counts as lodging. A meeting room does not.",
    "served_food": "Food or a non-alcoholic drink to eat or drink right away, such as a meal, coffee, room service, takeaway food, or snacks and soft drinks from a minibar.",
    "alcohol": "An alcoholic drink, such as beer, wine, cider or spirits, including from a minibar.",
    "transport": "A ride or a ticket that carries a person, such as a taxi, train, bus, ferry or flight, including a booking fee on the ticket.",
    "goods": "An item for work to take away, such as equipment or office supplies.",
    "private_item": "An item for the traveller's private use, such as clothing, cosmetics, perfume, toiletries, jewellery, toys, or films and other entertainment for the traveller.",
    "other_cost": "Another known cost, such as parking, fuel, car rental, a toll, a tip, a fee, a deposit, city tax or a rounding line.",
    "unclear": "The line does not say what was bought.",
}


def line_question_id(index: int) -> str:
    return f"line_{index + 1}"


def line_questions(lines: list[dict]) -> dict[str, dict]:
    """One choice per receipt line, built at request time from the lines."""
    return {
        line_question_id(i): {
            "type": "choice",
            "instructions": {"line": line["text"], "question": LINE_QUESTION},
            "criteria": dict(LINE_CRITERIA),
        }
        for i, line in enumerate(lines)
    }


def expense_request_questions(base: dict[str, dict], lines: list[dict]) -> dict[str, dict]:
    return merge_questions(base, line_questions(lines))


DUPLICATE_QUESTION = (
    "Does `invoice_text` charge for the same goods or services, from the same delivery "
    "or the same period, as `earlier_invoice`?"
)
DUPLICATE_CRITERIA = {
    "true": "The same items from the same delivery or period appear on `earlier_invoice`, for example the same delivery date or the same delivery note, or `invoice_text` refers to `earlier_invoice` by its invoice number.",
    "false": "The items are different, or they come from a different delivery or period. If neither text names a delivery date, delivery note or period, answer no.",
}


def duplicate_question_id(invoice_number: str) -> str:
    return "same_as_" + re.sub(r"[^0-9A-Za-z]+", "_", invoice_number).strip("_")


def duplicate_questions(earlier_invoices: list[dict]) -> dict[str, dict]:
    """One yes/no question per earlier invoice, built at request time from data.

    Raises QuestionCollision when two earlier invoices sanitise to the same question id,
    or when an invoice number sanitises to nothing at all.
    """
    questions: dict[str, dict] = {}
    for e in earlier_invoices:
        qid = duplicate_question_id(e["invoice_number"])
        if qid == "same_as_" or qid in questions:
            raise QuestionCollision(f"earlier invoices collide on question id: {qid}")
        questions[qid] = {
            "type": "noul",
            "instructions": {
                "earlier_invoice": {"invoice_number": e["invoice_number"], "text": e["text"]},
                "question": DUPLICATE_QUESTION,
            },
            "criteria": dict(DUPLICATE_CRITERIA),
        }
    return questions


def vendor_request_questions(base: dict[str, dict], earlier_invoices: list[dict]) -> dict[str, dict]:
    return merge_questions(base, duplicate_questions(earlier_invoices))
