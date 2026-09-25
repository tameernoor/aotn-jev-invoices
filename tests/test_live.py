"""One real call to Jev. Skipped unless TYPESAFE_API_KEY is set.

    uv run --env-file .env pytest -m live -v
"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jev_invoices.app import create_app
from jev_invoices.questions import load_questions
from jev_invoices.store import Store

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("TYPESAFE_API_KEY"), reason="needs TYPESAFE_API_KEY"),
]

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def test_taxi_sample_against_real_jev(tmp_path):
    sample = json.loads((SAMPLES / "expense" / "taxi.json").read_text(encoding="utf-8"))
    app = create_app(store=Store(tmp_path / "db.sqlite", tmp_path / "out"))
    with TestClient(app) as client:
        response = client.post("/expense-invoices", json=sample["request"])

    assert response.status_code == 200, response.text
    record = response.json()
    assert set(record["judgments"]) == set(load_questions("expense"))
    assert record["jev"]["model"].startswith("jev-")
    assert record["jev"]["input_tokens"] > 0
    assert record["jev"]["question_count"] == 8
