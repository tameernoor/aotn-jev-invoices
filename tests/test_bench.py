import json
from pathlib import Path

from fakes import answers, level

from jev_invoices.bench import (
    OUT_FILE,
    SAMPLES_DIR,
    computed_check,
    load_samples,
    out_file_for,
    score,
    summarise,
    to_json,
)


def test_score_uses_the_apps_thresholds_and_reports_uncertain_separately():
    judgments = answers(
        food_for_several=0.9, diners_named=0.5, purpose_fits_receipt=0.1, receipt_kind="proof_of_purchase"
    )
    result = score(
        judgments,
        {
            "food_for_several": True,
            "diners_named": True,
            "purpose_fits_receipt": True,
            "receipt_kind": "proof_of_purchase",
        },
    )
    assert result == {
        "correct": 2, "uncertain": ["diners_named"], "misses": ["purpose_fits_receipt"], "total": 4
    }


def test_score_scores_a_score_level_hit_and_miss():
    judgments = answers(line_specificity=level(2))
    hit = score(judgments, {"line_specificity": 2})
    assert hit == {"correct": 1, "uncertain": [], "misses": [], "total": 1}

    miss = score(judgments, {"line_specificity": 1})
    assert miss == {"correct": 0, "uncertain": [], "misses": ["line_specificity"], "total": 1}


def test_score_level_boundary_matches_the_rules_half_open_treatment():
    # The rules treat a score value as level 1 when 0.5 <= value < 1.5 (constraints.md).
    # The lower bound is inclusive, the upper bound is not.
    lower_bound = {"line_specificity": {"type": "score", "value": 0.5}}
    assert score(lower_bound, {"line_specificity": 1}) == {
        "correct": 1, "uncertain": [], "misses": [], "total": 1
    }

    upper_bound = {"line_specificity": {"type": "score", "value": 1.5}}
    assert score(upper_bound, {"line_specificity": 1}) == {
        "correct": 0, "uncertain": [], "misses": ["line_specificity"], "total": 1
    }


def test_score_counts_a_low_confidence_choice_as_uncertain():
    judgments = {"document_kind": {"type": "choice", "value": "invoice", "confidence": 0.4}}
    result = score(judgments, {"document_kind": "invoice"})
    assert result == {"correct": 0, "uncertain": ["document_kind"], "misses": [], "total": 1}


def test_computed_check_runs_the_real_rules_and_reports_differences():
    sample = json.loads((SAMPLES_DIR / "expense" / "taxi.json").read_text(encoding="utf-8"))
    judgments = answers(
        food_for_several=0.05,
        diners_named=0.05,
        purpose_fits_receipt=0.95,
        receipt_kind="proof_of_purchase",
        purpose_detail=level(1),
        line_1="transport",
    )
    matching = computed_check("expense", sample["request"], judgments, sample["expected"]["computed"])
    assert matching == {"matches": True, "differences": {}}

    judgments["purpose_fits_receipt"] = {"type": "noul", "value": 0.05}
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
            "uncertain": ["diners_named"],
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


def test_load_samples_reads_expense_and_vendor_json_from_a_given_directory(tmp_path):
    (tmp_path / "expense").mkdir()
    (tmp_path / "vendor").mkdir()
    (tmp_path / "expense" / "one.json").write_text(json.dumps({"name": "one"}), encoding="utf-8")
    (tmp_path / "vendor" / "two.json").write_text(json.dumps({"name": "two"}), encoding="utf-8")

    result = load_samples(tmp_path)

    assert result == [("expense", {"name": "one"}), ("vendor", {"name": "two"})]


def test_out_file_for_default_samples_dir_is_the_plain_out_file():
    assert out_file_for(SAMPLES_DIR) == OUT_FILE


def test_out_file_for_another_folder_is_named_after_it():
    assert out_file_for(SAMPLES_DIR.parent / "samples" / "holdout") == Path("out/bench-holdout.json")


def test_a_row_with_a_totals_by_code_mismatch_serialises_to_json():
    # line_1 answered "goods" instead of the expected "transport" moves the line's
    # Decimal amount into a different totals_by_code bucket, so both `lines` and
    # `totals_by_code` come back as mismatches, each carrying a real Decimal in `got`.
    sample = json.loads((SAMPLES_DIR / "expense" / "taxi.json").read_text(encoding="utf-8"))
    judgments = answers(
        food_for_several=0.05,
        diners_named=0.05,
        purpose_fits_receipt=0.95,
        receipt_kind="proof_of_purchase",
        purpose_detail=level(1),
        line_1="goods",
    )
    computed = computed_check("expense", sample["request"], judgments, sample["expected"]["computed"])
    assert computed["matches"] is False
    assert "totals_by_code" in computed["differences"]

    row = {
        "sample": sample["name"],
        "kind": "expense",
        "lang": "no",
        **score(judgments, sample["expected"]["judgments"]),
        "computed": computed,
        "judgments": judgments,
        "jev": {
            "model": "fake-jev",
            "request_id": None,
            "latency_ms": 1.0,
            "question_count": len(judgments),
            "input_tokens": 100,
            "price_per_mtok_usd": 0.042,
            "cost_usd": 0.0000042,
        },
    }

    text = to_json({"no": {}}, [row])  # must not raise

    assert json.loads(text)["rows"][0]["computed"]["differences"]["totals_by_code"] == {
        "expected": {"13": "845.00"},
        "got": {"1": "845.00"},
    }


def test_computed_check_ignores_line_text_so_the_english_run_still_matches():
    # The English bench run sends lines_en's translated text; the sample's expected
    # `lines` are written in the receipt's original language. amount, category and
    # saft_code all agree, so this must still count as a match.
    sample = json.loads((SAMPLES_DIR / "expense" / "taxi.json").read_text(encoding="utf-8"))
    request = {**sample["request"], "invoice_text": sample["text_en"], "lines": sample["lines_en"]}
    assert request["lines"][0]["text"] != sample["expected"]["computed"]["lines"][0]["text"]

    judgments = answers(
        food_for_several=0.05,
        diners_named=0.05,
        purpose_fits_receipt=0.95,
        receipt_kind="proof_of_purchase",
        purpose_detail=level(1),
        line_1="transport",
    )
    result = computed_check("expense", request, judgments, sample["expected"]["computed"])
    assert result == {"matches": True, "differences": {}}


def test_computed_check_matches_amounts_numerically_regardless_of_trailing_zeros():
    # A line amount of "845" (no decimals) must still match the sample's expected
    # "845.00" in both `lines` and `totals_by_code`, since they are the same amount.
    sample = json.loads((SAMPLES_DIR / "expense" / "taxi.json").read_text(encoding="utf-8"))
    line = {**sample["request"]["lines"][0], "amount": "845"}
    request = {**sample["request"], "lines": [line]}

    judgments = answers(
        food_for_several=0.05,
        diners_named=0.05,
        purpose_fits_receipt=0.95,
        receipt_kind="proof_of_purchase",
        purpose_detail=level(1),
        line_1="transport",
    )
    result = computed_check("expense", request, judgments, sample["expected"]["computed"])
    assert result == {"matches": True, "differences": {}}
