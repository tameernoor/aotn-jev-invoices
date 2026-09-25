"""Does Jev read Norwegian invoices as well as English ones?

Runs every sample against real Jev twice, with the Norwegian text and with the English
translation, scores the answers at the app's own thresholds, and checks the rules'
output against each sample's expected result.

    uv run --env-file .env python -m jev_invoices.bench
"""

import asyncio
import json
from pathlib import Path

from .jev import Jev
from .models import ExpenseInvoiceIn, VendorInvoiceIn
from .questions import load_questions
from .rules.expense import apply_tax_rules
from .rules.judgments import NO, YES
from .rules.vendor import decide_vendor, exact_checks

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
    """Score judgments at the app's own thresholds (YES/NO from rules.judgments).

    An expected-true noul is correct only if its value is >= YES, an expected-false
    noul only if its value is <= NO. A value strictly between NO and YES is uncertain,
    neither correct nor a miss. Choices compare by equality.
    """
    correct = 0
    uncertain = []
    misses = []
    for qid, want in expected.items():
        got = judgments[qid]["value"]
        if isinstance(want, str):
            if got == want:
                correct += 1
            else:
                misses.append(qid)
            continue
        hit = got >= YES if want else got <= NO
        miss = got <= NO if want else got >= YES
        if hit:
            correct += 1
        elif miss:
            misses.append(qid)
        else:
            uncertain.append(qid)
    return {"correct": correct, "uncertain": uncertain, "misses": misses, "total": len(expected)}


def computed_check(kind: str, request_body: dict, judgments: dict, expected_computed: dict) -> dict:
    """Run the real rules on the real judgments, with the same arguments app.py passes."""
    body = REQUEST_MODELS[kind].model_validate(request_body)
    if kind == "expense":
        computed = apply_tax_rules(
            judgments,
            invoice_text=body.invoice_text,
            employee_country=body.employee_country,
            vendor_country=body.vendor_country,
        )
    else:
        checks = exact_checks(
            invoice_number=body.invoice_number,
            amount=body.amount,
            invoice_date=body.invoice_date,
            bank_account=body.bank_account,
            bank_account_on_file=body.vendor.bank_account_on_file,
            po_total=body.purchase_order.total,
            earlier_invoices=[e.model_dump() for e in body.earlier_invoices],
        )
        computed = decide_vendor(judgments, checks)

    differences = {
        key: {"expected": want, "got": computed.get(key)}
        for key, want in expected_computed.items()
        if computed.get(key) != want
    }
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
    questions = {kind: load_questions(kind) for kind in REQUEST_MODELS}
    rows = []
    try:
        for kind, sample in load_samples():
            for lang in ("no", "en"):
                request = dict(sample["request"])
                if lang == "en":
                    request["invoice_text"] = sample["text_en"]
                body = REQUEST_MODELS[kind].model_validate(request)
                result = await jev.ask(body.state(), questions[kind])
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


def main() -> None:
    rows = asyncio.run(run())
    summary = summarise(rows)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
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
