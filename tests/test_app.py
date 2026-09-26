import pytest
import typesafe_sdk as ts
from fakes import FakeJev
from fastapi.testclient import TestClient

from jev_invoices.app import create_app
from jev_invoices.jev import JevRejected, JevUnavailable
from jev_invoices.store import Store
from test_models_store import VENDOR_BODY

TAXI = {
    "invoice_text": "Taxi Nordlysveien AS\nÅ betale 845,00\nHerav mva 12 %  90,54",
    "lines": [{"text": "Tur: Oslo lufthavn - Majorstuen", "amount": "845.00"}],
    "employee_country": "NO",
    "vendor_country": "NO",
    "expense_purpose": "Hjemreise fra konferanse",
}


@pytest.fixture
def make_client(tmp_path):
    def make(fake: FakeJev) -> TestClient:
        store = Store(tmp_path / "invoices.sqlite", tmp_path / "out")
        return TestClient(create_app(ask=fake.ask, store=store))

    return make


def test_expense_invoice_is_judged_in_one_call_coded_and_saved(make_client, tmp_path):
    fake = FakeJev({"purpose_fits_receipt": 0.95, "line_1": "transport"})
    response = make_client(fake).post("/expense-invoices", json=TAXI)

    assert response.status_code == 200
    record = response.json()
    assert len(fake.calls) == 1
    assert "line_1" in fake.calls[0]["questions"]
    assert len(fake.calls[0]["questions"]) == 6
    assert fake.calls[0]["state"]["invoice_text"] == TAXI["invoice_text"]
    assert record["kind"] == "expense"
    assert record["computed"]["lines"][0]["saft_code"] == "13"
    assert record["computed"]["totals_by_code"] == {"13": "845.00"}
    assert record["computed"]["vat_rates_found"] == ["12"]
    assert record["jev"]["question_count"] == 6
    assert (tmp_path / "out" / f"{record['id']}.json").exists()


def test_extra_question_is_answered_in_the_same_call_and_ignored_by_the_rules(make_client):
    fake = FakeJev({"purpose_fits_receipt": 0.95, "line_1": "transport", "night_trip": 0.9})
    body = {**TAXI, "extra_questions": {"night_trip": {"type": "noul", "instructions": "Was this a night trip?"}}}
    record = make_client(fake).post("/expense-invoices", json=body).json()

    assert len(fake.calls) == 1
    assert "night_trip" in fake.calls[0]["questions"]
    assert record["judgments"]["night_trip"] == {
        "type": "noul", "value": 0.9, "probabilities": None, "confidence": None, "legend": None,
    }
    assert "night_trip" not in record["computed"]["judgments_read"]
    assert record["computed"]["lines"][0]["saft_code"] == "13"


def test_extra_question_reusing_a_builtin_id_is_422(make_client):
    body = {**TAXI, "extra_questions": {"hosted_guests": {"type": "noul", "instructions": "Guests?"}}}
    response = make_client(FakeJev()).post("/expense-invoices", json=body)
    assert response.status_code == 422
    assert "hosted_guests" in response.json()["detail"]


def test_extra_question_reusing_a_generated_line_id_is_422(make_client):
    body = {**TAXI, "extra_questions": {"line_1": {"type": "noul", "instructions": "Another line question?"}}}
    response = make_client(FakeJev()).post("/expense-invoices", json=body)
    assert response.status_code == 422
    assert "line_1" in response.json()["detail"]


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "score", "instructions": "x", "criteria": ["one"]},
        {"type": "choice", "instructions": "x", "criteria": {f"o{i}": None for i in range(256)}},
        {"type": "bogus", "instructions": "x"},
    ],
)
def test_malformed_extra_question_is_422_and_jev_is_not_called(make_client, bad):
    fake = FakeJev()
    response = make_client(fake).post("/expense-invoices", json={**TAXI, "extra_questions": {"q": bad}})
    assert response.status_code == 422
    assert fake.calls == []


def test_jev_rejecting_the_questions_is_422(make_client):
    response = make_client(FakeJev(error=JevRejected("bad"))).post("/expense-invoices", json=TAXI)
    assert response.status_code == 422


def test_jev_down_is_502_and_nothing_is_saved(make_client):
    client = make_client(FakeJev(error=JevUnavailable("down")))
    assert client.post("/expense-invoices", json=TAXI).status_code == 502
    assert client.get("/invoices").json() == []


def test_vendor_invoice_is_decided(make_client):
    fake = FakeJev({"po_items_billed": 0.95})
    record = make_client(fake).post("/vendor-invoices", json=VENDOR_BODY).json()
    assert record["kind"] == "vendor"
    assert record["computed"]["decision"] == "approve"
    assert "same_as_20877" in fake.calls[0]["questions"]
    assert set(fake.calls[0]["state"]) == {"invoice_text", "purchase_order"}


def test_extra_question_colliding_with_a_generated_duplicate_id_is_422(make_client):
    body = {**VENDOR_BODY, "extra_questions": {"same_as_20877": {"type": "noul", "instructions": "Same delivery?"}}}
    response = make_client(FakeJev()).post("/vendor-invoices", json=body)
    assert response.status_code == 422
    assert "same_as_20877" in response.json()["detail"]


def test_in_window_duplicate_answer_sends_the_invoice_to_review(make_client):
    # earlier invoice 20877 is dated 2026-08-12, 31 days before VENDOR_BODY's 2026-09-12: inside the window.
    fake = FakeJev({"po_items_billed": 0.95, "same_as_20877": 0.95})
    record = make_client(fake).post("/vendor-invoices", json=VENDOR_BODY).json()
    assert record["computed"]["decision"] == "review"
    assert any("20877" in reason for reason in record["computed"]["reasons"])


def test_out_of_window_earlier_invoice_gets_no_duplicate_question_and_approves(make_client):
    body = {
        **VENDOR_BODY,
        "earlier_invoices": [{**VENDOR_BODY["earlier_invoices"][0], "invoice_date": "2026-07-01"}],
    }
    fake = FakeJev({"po_items_billed": 0.95})
    record = make_client(fake).post("/vendor-invoices", json=body).json()
    assert "same_as_20877" not in fake.calls[0]["questions"]
    assert record["computed"]["decision"] == "approve"
    assert "same_as_20877" not in record["computed"]["judgments_read"]


def test_earlier_invoices_colliding_on_the_same_question_id_is_422(make_client):
    body = {
        **VENDOR_BODY,
        "earlier_invoices": [
            {"invoice_number": "INV-1", "invoice_date": "2026-09-01", "amount": "100.00", "text": "a"},
            {"invoice_number": "INV/1", "invoice_date": "2026-09-01", "amount": "100.00", "text": "b"},
        ],
    }
    response = make_client(FakeJev()).post("/vendor-invoices", json=body)
    assert response.status_code == 422


def test_more_than_fifty_earlier_invoices_is_422(make_client):
    earlier = [
        {"invoice_number": str(i), "invoice_date": "2026-09-01", "amount": "100.00", "text": "x"}
        for i in range(51)
    ]
    body = {**VENDOR_BODY, "earlier_invoices": earlier}
    response = make_client(FakeJev()).post("/vendor-invoices", json=body)
    assert response.status_code == 422


def test_vendor_jev_down_is_502_and_nothing_is_saved(make_client):
    client = make_client(FakeJev(error=JevUnavailable("down")))
    assert client.post("/vendor-invoices", json=VENDOR_BODY).status_code == 502
    assert client.get("/invoices").json() == []


def test_records_can_be_listed_and_fetched(make_client):
    client = make_client(FakeJev({"purpose_fits_receipt": 0.95, "line_1": "transport"}))
    first = client.post("/expense-invoices", json=TAXI).json()
    second = client.post("/expense-invoices", json=TAXI).json()
    assert [r["id"] for r in client.get("/invoices").json()] == [second["id"], first["id"]]
    assert client.get(f"/invoices/{first['id']}").json() == first
    assert client.get("/invoices/nope").status_code == 404


def test_app_refuses_to_start_without_a_key(monkeypatch, tmp_path):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(ts.TypeSafeError):
        create_app(store=Store(tmp_path / "db.sqlite", tmp_path / "out"))
