"""Does Jev read Norwegian invoices as well as English ones?

Runs every sample against real Jev twice, with the Norwegian text and with the English
translation, and compares the answers with the sample's expected judgments.

    uv run --env-file .env python -m jev_invoices.bench
"""

import asyncio
import json
from pathlib import Path

from .jev import Jev
from .models import ExpenseInvoiceIn, VendorInvoiceIn
from .questions import load_questions

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
    misses = []
    for qid, want in expected.items():
        got = judgments[qid]["value"]
        matched = got == want if isinstance(want, str) else (got >= 0.5) == want
        if not matched:
            misses.append(qid)
    return {"correct": len(expected) - len(misses), "total": len(expected), "misses": misses}


def summarise(rows: list[dict]) -> dict[str, dict]:
    summary = {}
    for lang in sorted({row["lang"] for row in rows}):
        mine = [row for row in rows if row["lang"] == lang]
        summary[lang] = {
            "correct": sum(row["correct"] for row in mine),
            "total": sum(row["total"] for row in mine),
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
            f"{lang}: {s['correct']}/{s['total']} judgments as expected, "
            f"mean {s['mean_latency_ms']} ms and {s['mean_input_tokens']} input tokens per invoice, "
            f"total ${s['total_cost_usd']:.6f}"
        )
    for row in rows:
        if row["misses"]:
            print(f"  {row['lang']} {row['sample']}: missed {', '.join(row['misses'])}")
    print(f"Saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
