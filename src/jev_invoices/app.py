"""HTTP API. Jev answers the questions, the rules decide, every record is saved.

Run with:  uv run --env-file .env uvicorn jev_invoices.app:create_app --factory
"""

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException

from .jev import AskFn, Jev, JevRejected, JevResult, JevUnavailable
from .models import (
    ExpenseComputed,
    ExpenseInvoiceIn,
    InvoiceRecord,
    JevMeta,
    VendorComputed,
    VendorInvoiceIn,
)
from .questions import (
    QuestionCollision,
    expense_request_questions,
    load_questions,
    merge_questions,
    vendor_request_questions,
)
from .rules.expense import apply_tax_rules
from .rules.vendor import decide_vendor, exact_checks, recent_invoices
from .store import Store


def create_app(ask: AskFn | None = None, store: Store | None = None) -> FastAPI:
    jev = None
    if ask is None:
        jev = Jev()  # raises TypeSafeError without TYPESAFE_API_KEY, so the app never starts keyless
        ask = jev.ask
    if store is None:
        store = Store(
            Path(os.environ.get("JEV_INVOICES_DB", "out/invoices.sqlite")),
            Path(os.environ.get("JEV_INVOICES_OUT", "out")),
        )
    expense_questions = load_questions("expense")
    vendor_questions = load_questions("vendor")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if jev is not None:
            await jev.aclose()

    app = FastAPI(
        title="jev-invoices",
        description="Jev judges invoices in one request per invoice. Plain code decides.",
        lifespan=lifespan,
    )

    async def judge(state: dict, base: dict[str, dict], extra: dict | None) -> JevResult:
        try:
            questions = merge_questions(base, extra)
        except QuestionCollision as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            return await ask(state, questions)
        except JevRejected as exc:
            raise HTTPException(status_code=422, detail=f"Jev rejected the questions: {exc}") from exc
        except JevUnavailable as exc:
            raise HTTPException(status_code=502, detail=f"Jev is unavailable: {exc}") from exc

    def save(kind: str, body, result: JevResult, computed) -> InvoiceRecord:
        record = InvoiceRecord(
            id=uuid4().hex,
            kind=kind,
            created_at=datetime.now(UTC),
            input=body.model_dump(mode="json"),
            judgments=result.judgments,
            computed=computed,
            jev=JevMeta(**result.meta),
        )
        store.save(record)
        return record

    @app.post("/expense-invoices", response_model=InvoiceRecord)
    async def post_expense_invoice(body: ExpenseInvoiceIn) -> InvoiceRecord:
        lines = [line.model_dump() for line in body.lines]
        base = expense_request_questions(expense_questions, lines)
        result = await judge(body.state(), base, body.extra_questions)
        computed = apply_tax_rules(
            result.judgments,
            lines=lines,
            invoice_text=body.invoice_text,
            employee_country=body.employee_country,
            vendor_country=body.vendor_country,
        )
        return save("expense", body, result, ExpenseComputed(**computed))

    @app.post("/vendor-invoices", response_model=InvoiceRecord)
    async def post_vendor_invoice(body: VendorInvoiceIn) -> InvoiceRecord:
        earlier = [e.model_dump() for e in body.earlier_invoices]
        recent = recent_invoices(body.invoice_date, earlier)
        try:
            base = vendor_request_questions(vendor_questions, [e for e in earlier if e["invoice_number"] in recent])
        except QuestionCollision as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result = await judge(body.state(), base, body.extra_questions)
        checks = exact_checks(
            invoice_number=body.invoice_number,
            amount=body.amount,
            bank_account=body.bank_account,
            bank_account_on_file=body.vendor.bank_account_on_file,
            po_total=body.purchase_order.total,
            earlier_invoices=earlier,
        )
        computed = decide_vendor(result.judgments, checks, recent)
        return save("vendor", body, result, VendorComputed(**computed))

    @app.get("/invoices", response_model=list[InvoiceRecord])
    def list_invoices(limit: int = 50) -> list[InvoiceRecord]:
        return store.recent(limit)

    @app.get("/invoices/{invoice_id}", response_model=InvoiceRecord)
    def get_invoice(invoice_id: str) -> InvoiceRecord:
        record = store.get(invoice_id)
        if record is None:
            raise HTTPException(status_code=404, detail="No invoice with that id.")
        return record

    return app
