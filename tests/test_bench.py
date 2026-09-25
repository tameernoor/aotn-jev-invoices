import json

from fakes import answers, level

from jev_invoices.bench import SAMPLES_DIR, computed_check, load_samples, score, summarise


def test_score_uses_the_apps_thresholds_and_reports_uncertain_separately():
    judgments = answers(alcohol=0.9, food=0.5, passenger_transport=0.1, category="food")
    result = score(judgments, {"alcohol": True, "food": True, "passenger_transport": True, "category": "food"})
    assert result == {"correct": 2, "uncertain": ["food"], "misses": ["passenger_transport"], "total": 4}


def test_score_scores_a_score_level_hit_and_miss():
    judgments = answers(line_specificity=level(2))
    hit = score(judgments, {"line_specificity": 2})
    assert hit == {"correct": 1, "uncertain": [], "misses": [], "total": 1}

    miss = score(judgments, {"line_specificity": 1})
    assert miss == {"correct": 0, "uncertain": [], "misses": ["line_specificity"], "total": 1}


def test_score_counts_a_low_confidence_choice_as_uncertain():
    judgments = {"document_kind": {"type": "choice", "value": "invoice", "confidence": 0.4}}
    result = score(judgments, {"document_kind": "invoice"})
    assert result == {"correct": 0, "uncertain": ["document_kind"], "misses": [], "total": 1}


def test_computed_check_runs_the_real_rules_and_reports_differences():
    sample = json.loads((SAMPLES_DIR / "expense" / "taxi.json").read_text(encoding="utf-8"))
    judgments = answers(
        lodging_charged=0.05,
        served_food_charged=0.05,
        alcohol_charged=0.05,
        transport_charged=0.95,
        goods_charged=0.05,
        hosted_guests=0.05,
        purpose_fits_receipt=0.95,
        personal_items=0.05,
        receipt_kind="proof_of_purchase",
        purpose_detail=level(1),
    )
    matching = computed_check("expense", sample["request"], judgments, sample["expected"]["computed"])
    assert matching == {"matches": True, "differences": {}}

    judgments["personal_items"] = {"type": "noul", "value": 0.95}
    mismatching = computed_check("expense", sample["request"], judgments, sample["expected"]["computed"])
    assert mismatching["matches"] is False
    assert mismatching["differences"] == {"needs_review": {"expected": False, "got": True}}


def test_computed_check_runs_the_real_vendor_rules_and_reports_differences():
    sample = json.loads((SAMPLES_DIR / "vendor" / "clean-invoice.json").read_text(encoding="utf-8"))
    judgments = answers(
        line_specificity=level(2),
        po_items_billed=0.95,
        unordered_items=0.05,
        bank_change_request=0.05,
        payment_pressure=0.05,
        document_kind="invoice",
        same_as_20877=0.05,
    )
    matching = computed_check("vendor", sample["request"], judgments, sample["expected"]["computed"])
    assert matching == {"matches": True, "differences": {}}

    judgments["bank_change_request"] = {"type": "noul", "value": 0.95}
    mismatching = computed_check("vendor", sample["request"], judgments, sample["expected"]["computed"])
    assert mismatching["matches"] is False
    assert mismatching["differences"] == {"decision": {"expected": "approve", "got": "hold"}}


def test_summarise_per_language():
    rows = [
        {
            "lang": "no",
            "correct": 6,
            "uncertain": ["food"],
            "misses": [],
            "total": 7,
            "computed": {"matches": True, "differences": {}},
            "jev": {"latency_ms": 100.0, "input_tokens": 1000, "cost_usd": 0.00004},
        },
        {
            "lang": "no",
            "correct": 7,
            "uncertain": [],
            "misses": [],
            "total": 7,
            "computed": {"matches": False, "differences": {"saft_code": {"expected": "1", "got": "0"}}},
            "jev": {"latency_ms": 300.0, "input_tokens": 3000, "cost_usd": 0.00012},
        },
        {
            "lang": "en",
            "correct": 7,
            "uncertain": [],
            "misses": [],
            "total": 7,
            "computed": {"matches": True, "differences": {}},
            "jev": {"latency_ms": 200.0, "input_tokens": 2000, "cost_usd": 0.00008},
        },
    ]
    summary = summarise(rows)
    assert summary["no"] == {
        "correct": 13,
        "uncertain": 1,
        "misses": 0,
        "total": 14,
        "computed_matches": 1,
        "rows": 2,
        "mean_latency_ms": 200.0,
        "mean_input_tokens": 2000.0,
        "total_cost_usd": 0.00016,
    }
    assert summary["en"]["correct"] == 7
    assert summary["en"]["computed_matches"] == 1
    assert summary["en"]["rows"] == 1


def test_load_samples_finds_both_kinds():
    kinds = [kind for kind, _ in load_samples()]
    assert kinds.count("expense") == 9
    assert kinds.count("vendor") == 7
