"""Does Jev read Norwegian invoices as well as English ones?

Runs every sample against real Jev twice, with the Norwegian text and with the English
translation, scores the answers at the app's own thresholds, and checks the rules'
output against each sample's expected result.

    uv run --env-file .env python -m jev_invoices.bench
"""

import asyncio
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .jev import Jev
from .models import ExpenseInvoiceIn, VendorInvoiceIn
from .questions import expense_request_questions, load_questions, vendor_request_questions
from .rules.expense import apply_tax_rules
from .rules.judgments import CHOICE_MIN_CONFIDENCE, NO, YES
from .rules.vendor import decide_vendor, exact_checks, recent_invoices

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"
OUT_FILE = Path("out/bench.json")
REQUEST_MODELS = {"expense": ExpenseInvoiceIn, "vendor": VendorInvoiceIn}


def load_samples(directory: Path = SAMPLES_DIR) -> list[tuple[str, dict]]:
    return [
        (kind, json.loads(path.read_text(encoding="utf-8")))
        for kind in ("expense", "vendor")
        for path in sorted((directory / kind).glob("*.json"))
    ]


def score(judgments: dict, expected: dict) -> dict:
    """Score judgments at the app's own thresholds.

    A noul (bool expected) is correct only if its value is >= YES when the expectation is
    true, or <= NO when it is false; a value strictly between NO and YES is uncertain,
    neither correct nor a miss. A choice (str expected) is correct on an exact match; one
    read with confidence below CHOICE_MIN_CONFIDENCE counts as uncertain instead, whatever
    its value. A score level (int expected) is correct when `level - 0.5 <= value < level +
    0.5`, the same half-open halfway points the rules use, otherwise a miss; levels are
    never uncertain. Booleans are checked before ints, since bool is a subtype of int in
    Python.
    """
    correct = 0
    uncertain = []
    misses = []
    for qid, want in expected.items():
        answer = judgments[qid]
        if isinstance(want, bool):
            value = answer["value"]
            hit = value >= YES if want else value <= NO
            miss = value <= NO if want else value >= YES
            if hit:
                correct += 1
            elif miss:
                misses.append(qid)
            else:
                uncertain.append(qid)
        elif isinstance(want, str):
            if answer.get("confidence", 1.0) < CHOICE_MIN_CONFIDENCE:
                uncertain.append(qid)
            elif answer["value"] == want:
                correct += 1
            else:
                misses.append(qid)
        else:  # int: a score level
            if want - 0.5 <= answer["value"] < want + 0.5:
                correct += 1
            else:
                misses.append(qid)
    return {"correct": correct, "uncertain": uncertain, "misses": misses, "total": len(expected)}


def _decimal_safe(value):
    """Recursively canonicalise Decimal amounts and decimal-shaped strings to str(Decimal(x)),
    so a JSON-loaded expected value (amounts as strings) and a real Decimal from the rules
    compare equal regardless of which side they came from."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        try:
            return str(Decimal(value))
        except InvalidOperation:
            return value
    if isinstance(value, dict):
        return {k: _decimal_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decimal_safe(v) for v in value]
    return value


def _lines_without_text(value):
    """Drop each coded line's `text`, so the English bench run (whose request carries
    `lines_en`'s translated text) can still match a sample's expected `lines`, which are
    written in the receipt's original language. amount, category and saft_code still
    have to agree."""
    if not isinstance(value, list):
        return value
    return [{k: v for k, v in line.items() if k != "text"} if isinstance(line, dict) else line for line in value]


def computed_check(kind: str, request_body: dict, judgments: dict, expected_computed: dict) -> dict:
    """Run the real rules on the real judgments, with the same arguments app.py passes."""
    body = REQUEST_MODELS[kind].model_validate(request_body)
    if kind == "expense":
        lines = [line.model_dump() for line in body.lines]
        computed = apply_tax_rules(
            judgments,
            lines=lines,
            invoice_text=body.invoice_text,
            employee_country=body.employee_country,
            vendor_country=body.vendor_country,
        )
    else:
        earlier = [e.model_dump() for e in body.earlier_invoices]
        checks = exact_checks(
            invoice_number=body.invoice_number,
            amount=body.amount,
            bank_account=body.bank_account,
            bank_account_on_file=body.vendor.bank_account_on_file,
            po_total=body.purchase_order.total,
            earlier_invoices=earlier,
        )
        recent = recent_invoices(body.invoice_date, earlier)
        computed = decide_vendor(judgments, checks, recent)

    differences = {}
    for key, want in expected_computed.items():
        got = computed.get(key)
        if key == "lines":
            want, got = _lines_without_text(want), _lines_without_text(got)
        want_safe = _decimal_safe(want)
        got_safe = _decimal_safe(got)
        if got_safe != want_safe:
            differences[key] = {"expected": want_safe, "got": got_safe}
    return {"matches": not differences, "differences": differences}


def summarise(rows: list[dict]) -> dict[str, dict]:
    summary = {}
    for lang in sorted({row["lang"] for row in rows}):
        mine = [row for row in rows if row["lang"] == lang]
        summary[lang] = {
            "correct": sum(row["correct"] for row in mine),
            "uncertain": sum(len(row["uncertain"]) for row in mine),
            "misses": sum(len(row["misses"]) for row in mine),
            "total": sum(row["total"] for row in mine),
            "computed_matches": sum(1 for row in mine if row["computed"]["matches"]),
            "rows": len(mine),
            "mean_latency_ms": round(sum(row["jev"]["latency_ms"] for row in mine) / len(mine), 1),
            "mean_input_tokens": round(sum(row["jev"]["input_tokens"] for row in mine) / len(mine), 1),
            "total_cost_usd": round(sum(row["jev"]["cost_usd"] for row in mine), 8),
        }
    return summary


async def run() -> list[dict]:
    jev = Jev()
    expense_questions = load_questions("expense")
    vendor_questions = load_questions("vendor")
    rows = []
    try:
        for kind, sample in load_samples():
            for lang in ("no", "en"):
                request = dict(sample["request"])
                if lang == "en":
                    request["invoice_text"] = sample["text_en"]
                    if kind == "expense":
                        request["lines"] = sample["lines_en"]
                body = REQUEST_MODELS[kind].model_validate(request)
                if kind == "expense":
                    questions = expense_request_questions(
                        expense_questions, [line.model_dump() for line in body.lines]
                    )
                else:
                    earlier = [e.model_dump() for e in body.earlier_invoices]
                    recent = recent_invoices(body.invoice_date, earlier)
                    questions = vendor_request_questions(
                        vendor_questions, [e for e in earlier if e["invoice_number"] in recent]
                    )
                result = await jev.ask(body.state(), questions)
                rows.append(
                    {
                        "sample": sample["name"],
                        "kind": kind,
                        "lang": lang,
                        **score(result.judgments, sample["expected"]["judgments"]),
                        "computed": computed_check(kind, request, result.judgments, sample["expected"]["computed"]),
                        "judgments": result.judgments,
                        "jev": result.meta,
                    }
                )
    finally:
        await jev.aclose()
    return rows


def to_json(summary: dict, rows: list[dict]) -> str:
    """The exact serialisation main() writes to OUT_FILE, pulled out so it can be tested
    without a real Jev call. Every value reaching here must already be JSON-safe;
    computed_check() is what keeps Decimal amounts out of `rows`."""
    return json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False)


def main() -> None:
    rows = asyncio.run(run())
    summary = summarise(rows)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(to_json(summary, rows), encoding="utf-8")
    for lang, s in summary.items():
        print(
            f"{lang}: {s['correct']}/{s['total']} correct, {s['uncertain']} uncertain, {s['misses']} missed, "
            f"{s['computed_matches']}/{s['rows']} rows with matching computed values, "
            f"mean {s['mean_latency_ms']} ms and {s['mean_input_tokens']} input tokens per invoice, "
            f"total ${s['total_cost_usd']:.6f}"
        )
    for row in rows:
        problems = []
        if row["uncertain"]:
            problems.append(f"uncertain: {', '.join(row['uncertain'])}")
        if row["misses"]:
            problems.append(f"missed: {', '.join(row['misses'])}")
        if not row["computed"]["matches"]:
            problems.append(f"computed differs: {', '.join(row['computed']['differences'])}")
        if problems:
            print(f"  {row['lang']} {row['sample']}: {'; '.join(problems)}")
    print(f"Saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
