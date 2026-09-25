"""Each sample, answered with its own expected judgments, must produce its expected computed values.

This checks the rules end to end. Whether Jev gives those judgments is the bench's job.
"""

import json
from pathlib import Path

import pytest
from fakes import FakeJev
from fastapi.testclient import TestClient

from jev_invoices.app import create_app
from jev_invoices.questions import load_questions
from jev_invoices.store import Store

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
FILES = sorted(SAMPLES.glob("expense/*.json")) + sorted(SAMPLES.glob("vendor/*.json"))


def fake_values(expected_judgments: dict) -> dict:
    return {
        qid: want if isinstance(want, str) else (0.95 if want else 0.05)
        for qid, want in expected_judgments.items()
    }


def test_there_are_ten_samples():
    assert len(FILES) == 10


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_sample_expectations_cover_every_question(path):
    sample = json.loads(path.read_text(encoding="utf-8"))
    kind = path.parent.name
    asked = {qid for qid, q in load_questions(kind).items() if q["type"] != "score"}
    assert set(sample["expected"]["judgments"]) == asked


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_sample_produces_expected_computed_values(path, tmp_path):
    sample = json.loads(path.read_text(encoding="utf-8"))
    kind = path.parent.name
    fake = FakeJev(fake_values(sample["expected"]["judgments"]))
    client = TestClient(create_app(ask=fake.ask, store=Store(tmp_path / "db.sqlite", tmp_path / "out")))

    response = client.post(f"/{kind}-invoices", json=sample["request"])

    assert response.status_code == 200, response.text
    computed = response.json()["computed"]
    for key, want in sample["expected"]["computed"].items():
        assert computed[key] == want, f"{path.stem}: {key}"
