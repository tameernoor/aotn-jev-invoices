"""Each sample, answered with its own expected judgments, must produce its expected computed values.

This checks the rules end to end. Whether Jev gives those judgments is the bench's job.
"""

import json
from pathlib import Path

import pytest
from fakes import FakeJev
from fastapi.testclient import TestClient

from jev_invoices.app import create_app
from jev_invoices.questions import load_questions, vendor_request_questions
from jev_invoices.store import Store

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
FILES = sorted(SAMPLES.glob("expense/*.json")) + sorted(SAMPLES.glob("vendor/*.json"))


def fake_values(expected_judgments: dict) -> dict:
    """Expected judgment values, in the shape FakeJev's `values` map accepts:
    bool -> 0.95/0.05 (noul), str -> the choice unchanged, int -> a float score level."""
    out = {}
    for qid, want in expected_judgments.items():
        if isinstance(want, bool):
            out[qid] = 0.95 if want else 0.05
        elif isinstance(want, str):
            out[qid] = want
        else:
            out[qid] = float(want)
    return out


def asked_ids(kind: str, request: dict) -> set[str]:
    if kind == "vendor":
        return set(vendor_request_questions(load_questions("vendor"), request.get("earlier_invoices", [])))
    return set(load_questions(kind))


def test_there_are_sixteen_samples():
    assert len(FILES) == 16


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_sample_expectations_cover_every_question(path):
    sample = json.loads(path.read_text(encoding="utf-8"))
    kind = path.parent.name
    assert set(sample["expected"]["judgments"]) == asked_ids(kind, sample["request"])


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_sample_produces_expected_computed_values(path, tmp_path):
    sample = json.loads(path.read_text(encoding="utf-8"))
    kind = path.parent.name
    fake = FakeJev(fake_values(sample["expected"]["judgments"]))
    client = TestClient(create_app(ask=fake.ask, store=Store(tmp_path / "db.sqlite", tmp_path / "out")))

    response = client.post(f"/{kind}-invoices", json=sample["request"])

    assert response.status_code == 200, response.text
    assert set(fake.calls[0]["questions"]) == set(sample["expected"]["judgments"])
    computed = response.json()["computed"]
    for key, want in sample["expected"]["computed"].items():
        assert computed[key] == want, f"{path.stem}: {key}"
