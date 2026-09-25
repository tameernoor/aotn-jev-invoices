from fakes import answers

from jev_invoices.bench import load_samples, score, summarise


def test_score_uses_half_as_the_line_for_nouls_and_equality_for_choices():
    judgments = answers(alcohol=0.7, food=0.3, category="food")
    result = score(judgments, {"alcohol": True, "food": True, "category": "food"})
    assert result == {"correct": 2, "total": 3, "misses": ["food"]}


def test_summarise_per_language():
    rows = [
        {"lang": "no", "correct": 6, "total": 7, "jev": {"latency_ms": 100.0, "input_tokens": 1000, "cost_usd": 0.00004}},
        {"lang": "no", "correct": 7, "total": 7, "jev": {"latency_ms": 300.0, "input_tokens": 3000, "cost_usd": 0.00012}},
        {"lang": "en", "correct": 7, "total": 7, "jev": {"latency_ms": 200.0, "input_tokens": 2000, "cost_usd": 0.00008}},
    ]
    summary = summarise(rows)
    assert summary["no"] == {
        "correct": 13,
        "total": 14,
        "mean_latency_ms": 200.0,
        "mean_input_tokens": 2000.0,
        "total_cost_usd": 0.00016,
    }
    assert summary["en"]["correct"] == 7


def test_load_samples_finds_both_kinds():
    kinds = [kind for kind, _ in load_samples()]
    assert kinds.count("expense") == 6
    assert kinds.count("vendor") == 4
