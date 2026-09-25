import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jev_invoices.models import ExpenseComputed, ExpenseInvoiceIn, InvoiceRecord, JevMeta, VendorInvoiceIn
from jev_invoices.store import Store

VENDOR_BODY = {
    "invoice_text": "Faktura 20931",
    "invoice_number": "20931",
    "amount": "4170.00",
    "currency": "NOK",
    "invoice_date": "2026-09-12",
    "due_date": "2026-10-12",
    "bank_account": "1503.12.34567",
    "vendor": {"name": "Nordlys Kontorservice AS", "org_number": "999 200 001", "bank_account_on_file": "1503.12.34567"},
    "purchase_order": {
        "number": "PO-2026-118",
        "lines": [{"description": "Kaffebønner, hele, 1 kg", "quantity": "20", "unit_price": "189.00"}],
        "total": "4170.00",
    },
    "earlier_invoices": [
        {"invoice_number": "20877", "invoice_date": "2026-08-12", "amount": "3950.00", "text": "Faktura 20877"}
    ],
}


def make_record(record_id="r1", created_at=datetime(2026, 9, 25, 12, 0, tzinfo=UTC)):
    return InvoiceRecord(
        id=record_id,
        kind="expense",
        created_at=created_at,
        input={"invoice_text": "x"},
        judgments={"alcohol": {"type": "noul", "value": 0.9}},
        computed=ExpenseComputed(
            saft_code="1",
            category_check="agrees",
            should_split=False,
            foreign_purchase=False,
            vat_rates_found=["25"],
            needs_review=False,
            judgments_read=["alcohol"],
            uncertain=[],
            reasons=["Other purchase: deductible at the regular rate (25 %)."],
        ),
        jev=JevMeta(
            model="fake-jev",
            request_id=None,
            latency_ms=1.0,
            question_count=1,
            input_tokens=100,
            price_per_mtok_usd=0.042,
            cost_usd=0.0000042,
        ),
    )


def test_expense_state_leaves_out_extra_questions():
    body = ExpenseInvoiceIn(
        invoice_text="Taxi",
        employee_country="NO",
        vendor_country="NO",
        extra_questions={"q": {"type": "noul", "instructions": "Night trip?"}},
    )
    assert body.state() == {
        "invoice_text": "Taxi",
        "employee_country": "NO",
        "vendor_country": "NO",
        "expense_purpose": None,
    }


def test_country_codes_must_be_two_letters():
    with pytest.raises(ValidationError):
        ExpenseInvoiceIn(invoice_text="x", employee_country="NOR", vendor_country="NO")


def test_vendor_state_holds_descriptions_not_amounts_or_accounts():
    state = VendorInvoiceIn.model_validate(VENDOR_BODY).state()
    assert set(state) == {"invoice_text", "purchase_order", "earlier_invoices"}
    assert state["purchase_order"] == {
        "number": "PO-2026-118",
        "lines": [{"description": "Kaffebønner, hele, 1 kg"}],
    }
    assert state["earlier_invoices"] == [{"invoice_number": "20877", "text": "Faktura 20877"}]
    json.dumps(state)  # must be JSON-serialisable for the SDK


def test_store_round_trip_writes_sqlite_and_json(tmp_path):
    store = Store(tmp_path / "db" / "invoices.sqlite", tmp_path / "out")
    record = make_record()
    store.save(record)
    assert store.get("r1") == record
    written = json.loads((tmp_path / "out" / "r1.json").read_text(encoding="utf-8"))
    assert written["computed"]["saft_code"] == "1"


def test_store_lists_newest_first_and_misses_return_none(tmp_path):
    store = Store(tmp_path / "invoices.sqlite", tmp_path / "out")
    store.save(make_record("old", datetime(2026, 9, 24, tzinfo=UTC)))
    store.save(make_record("new", datetime(2026, 9, 25, tzinfo=UTC)))
    assert [r.id for r in store.recent()] == ["new", "old"]
    assert store.get("missing") is None
