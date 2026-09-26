"""A stand-in for Jev in tests. Answers every question it is asked, records every call."""

from jev_invoices.jev import JevResult


def level(n: int) -> dict:
    """A score judgment at level n, for building fixed answers with answers(qid=level(n))."""
    return {"type": "score", "value": float(n), "probabilities": {str(n): 1.0}, "confidence": 1.0, "legend": {}}


def answers(**values) -> dict:
    """Judgments in the shape jev.py returns. A float is a noul, a str is a choice (confidence 1.0),
    a dict (such as one built by level()) passes through unchanged."""
    out = {}
    for qid, value in values.items():
        if isinstance(value, dict):
            out[qid] = value
        elif isinstance(value, str):
            out[qid] = {"type": "choice", "value": value, "probabilities": {value: 1.0}, "confidence": 1.0}
        else:
            out[qid] = {"type": "noul", "value": float(value)}
    return out


class FakeJev:
    def __init__(self, values: dict | None = None, error: Exception | None = None):
        self.values = values or {}
        self.error = error
        self.calls: list[dict] = []

    async def ask(self, state: dict, questions: dict[str, dict]) -> JevResult:
        self.calls.append({"state": state, "questions": questions})
        if self.error is not None:
            raise self.error
        judgments = {}
        for qid, question in questions.items():
            value = self.values.get(qid)
            if question["type"] == "noul":
                judgments[qid] = {"type": "noul", "value": 0.05 if value is None else float(value)}
            elif question["type"] == "choice":
                options = question["criteria"]
                picked = value if value is not None else next(iter(options))
                judgments[qid] = {"type": "choice", "value": picked, "probabilities": {picked: 1.0}, "confidence": 1.0}
            else:
                # Default to the top level so unrelated tests don't trip a purpose/detail check
                # by accident; an explicit value in `values` always wins.
                top_level = float(len(question["criteria"]) - 1)
                picked_level = top_level if value is None else float(value)
                judgments[qid] = {
                    "type": "score",
                    "value": picked_level,
                    "probabilities": {str(int(picked_level)): 1.0},
                    "confidence": 1.0,
                    "legend": {str(i): str(lvl) for i, lvl in enumerate(question["criteria"])},
                }
        meta = {
            "model": "fake-jev",
            "request_id": None,
            "latency_ms": 1.0,
            "question_count": len(questions),
            "input_tokens": 100,
            "price_per_mtok_usd": 0.042,
            "cost_usd": 100 * 0.042 / 1_000_000,
        }
        return JevResult(judgments=judgments, meta=meta)
