"""Question sets. The YAML files define the classifiers; requests can add more."""

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
    return {qid: question.model_dump(exclude_none=True) for qid, question in questions.items()}


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
