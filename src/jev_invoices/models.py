"""Request types and InvoiceRecord, the contract downstream applications rely on.

A record keeps what Jev judged (`judgments`) apart from what code derived (`computed`).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from .questions import Question


class ExpenseInvoiceIn(BaseModel):
    invoice_text: str = Field(min_length=1)
    employee_country: str = Field(min_length=2, max_length=2, description="ISO 3166 alpha-2, e.g. NO")
    vendor_country: str = Field(min_length=2, max_length=2)
    expense_purpose: str | None = None
    extra_questions: dict[str, Question] | None = None

    def state(self) -> dict:
        return self.model_dump(mode="json", exclude={"extra_questions"})


class VendorRecord(BaseModel):
    name: str
    org_number: str
    bank_account_on_file: str


class POLine(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal


class PurchaseOrder(BaseModel):
    number: str
    lines: list[POLine]
    total: Decimal


class EarlierInvoice(BaseModel):
    invoice_number: str
    invoice_date: date
    amount: Decimal
    text: str


class VendorInvoiceIn(BaseModel):
    invoice_text: str = Field(min_length=1)
    invoice_number: str
    amount: Decimal
    currency: str
    invoice_date: date
    due_date: date
    bank_account: str
    vendor: VendorRecord
    purchase_order: PurchaseOrder
    earlier_invoices: list[EarlierInvoice] = []
    extra_questions: dict[str, Question] | None = None

    def state(self) -> dict:
        """What Jev sees: descriptions only. Amounts, dates and accounts stay with the code."""
        return {
            "invoice_text": self.invoice_text,
            "purchase_order": {
                "number": self.purchase_order.number,
                "lines": [{"description": line.description} for line in self.purchase_order.lines],
            },
            "earlier_invoices": [
                e.model_dump(mode="json", include={"invoice_number", "text"}) for e in self.earlier_invoices
            ],
        }


class Judgment(BaseModel):
    type: Literal["noul", "choice", "score"]
    value: float | str
    probabilities: dict[str, float] | None = None
    confidence: float | None = None
    legend: dict[str, str] | None = None


class ExpenseComputed(BaseModel):
    saft_code: str | None
    category_check: Literal["agrees", "disagrees", "not_checked"]
    should_split: bool
    foreign_purchase: bool
    vat_rates_found: list[str]
    needs_review: bool
    judgments_read: list[str]
    uncertain: list[str]
    reasons: list[str]


class VendorComputed(BaseModel):
    decision: Literal["approve", "hold", "review"]
    checks: dict[str, bool]
    judgments_read: list[str]
    uncertain: list[str]
    reasons: list[str]


class JevMeta(BaseModel):
    model: str
    request_id: str | None
    latency_ms: float
    question_count: int
    input_tokens: int
    price_per_mtok_usd: float
    cost_usd: float


class InvoiceRecord(BaseModel):
    id: str
    kind: Literal["expense", "vendor"]
    created_at: datetime
    input: dict[str, Any]
    judgments: dict[str, Judgment]
    computed: ExpenseComputed | VendorComputed
    jev: JevMeta
