"""A stand-in for Jev in tests. Answers every question it is asked, records every call."""

from jev_invoices.jev import JevResult


def answers(**values) -> dict:
    """Judgments in the shape jev.py returns. A float is a noul, a str is a choice."""
    out = {}
    for qid, value in values.items():
        if isinstance(value, str):
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
                picked = value if value is not None else ("other" if "other" in options else next(iter(options)))
                judgments[qid] = {"type": "choice", "value": picked, "probabilities": {picked: 1.0}, "confidence": 1.0}
            else:
                judgments[qid] = {
                    "type": "score",
                    "value": 0.0 if value is None else float(value),
                    "probabilities": {"0": 1.0},
                    "confidence": 1.0,
                    "legend": {str(i): str(level) for i, level in enumerate(question["criteria"])},
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
