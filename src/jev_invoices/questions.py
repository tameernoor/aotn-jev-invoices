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


DUPLICATE_QUESTION = (
    "Does `invoice_text` charge for the same goods or services, from the same delivery "
    "or the same period, as `earlier_invoice`?"
)
DUPLICATE_CRITERIA = {
    "true": "The same items from the same delivery or period appear on `earlier_invoice`, for example the same delivery date or the same delivery note.",
    "false": "The items are different, or they come from a different delivery or period. If neither text names a delivery date, delivery note or period, answer no.",
}


def duplicate_question_id(invoice_number: str) -> str:
    return "same_as_" + re.sub(r"[^0-9A-Za-z]+", "_", invoice_number).strip("_")


def duplicate_questions(earlier_invoices: list[dict]) -> dict[str, dict]:
    """One yes/no question per earlier invoice, built at request time from data."""
    return {
        duplicate_question_id(e["invoice_number"]): {
            "type": "noul",
            "instructions": {
                "earlier_invoice": {"invoice_number": e["invoice_number"], "text": e["text"]},
                "question": DUPLICATE_QUESTION,
            },
            "criteria": dict(DUPLICATE_CRITERIA),
        }
        for e in earlier_invoices
    }


def vendor_request_questions(base: dict[str, dict], earlier_invoices: list[dict]) -> dict[str, dict]:
    return merge_questions(base, duplicate_questions(earlier_invoices))
