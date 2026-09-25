# jev-invoices

Companion code for the article "The classifier you don't have to train".

Jev, TypeSafe AI's System One model, answers narrow questions about an invoice. Is it accommodation? Is there alcohol? Does the text announce a new bank account? Plain Python rules turn those answers into a VAT code or an approve, hold or review decision. The model never sees the rules, and the rules never call the model.

## What it shows

- **One request per invoice.** Every question for an invoice goes to Jev in a single request. Jev reads the invoice once and answers all the questions in parallel on its side. Some answers turn out not to matter for a given invoice, and the code simply ignores them.
- **Classifiers defined at runtime.** The questions live in `questions/expense.yaml` and `questions/vendor.yaml`. A new classifier is a new entry there, or an `extra_questions` field on a single request. Vendor invoices also get one generated question per earlier invoice, built from the request data rather than the YAML. Nothing is trained.
- **Policy stays in code.** `src/jev_invoices/rules/` holds the VAT and approval rules as ordinary functions. Each record lists which answers the rules actually read, and only those can send an invoice to review.

## The questions

Each question targets one known expense or accounts-payable problem. Ids are never sent to the model, so each instruction carries the whole question; the rules in `src/jev_invoices/rules/` are the only code that reads an id.

### Expense (`questions/expense.yaml`)

| id | type | what it catches |
|---|---|---|
| `lodging_charged` | noul | A night of accommodation, billed at the low VAT rate. |
| `served_food_charged` | noul | Restaurant meals, room service or minibar snacks, which get no VAT deduction. |
| `alcohol_charged` | noul | Alcoholic drinks, treated the same as served food. |
| `transport_charged` | noul | A taxi ride or travel ticket, billed at the low VAT rate, kept apart from parking or fuel. |
| `goods_charged` | noul | Goods taken away, billed at the regular VAT rate. |
| `hosted_guests` | noul | Customer entertainment (representasjon), which gets no VAT deduction. |
| `guests_named` | noul | An entertainment claim that does not name who was hosted. |
| `purpose_fits_receipt` | noul | A stated purpose that does not match what was actually bought. |
| `personal_items` | noul | Private items, such as clothing or cosmetics, charged as a business expense. |
| `receipt_kind` | choice | A document that is not valid proof of purchase, such as a card slip or a booking confirmation. |
| `purpose_detail` | score | A purpose that is missing or too generic to justify the expense. |

### Vendor (`questions/vendor.yaml`)

| id | type | what it catches |
|---|---|---|
| `line_specificity` | score | Invoice lines too vague to check against the purchase order, such as "miscellaneous services". |
| `po_items_billed` | noul | Lines that do not describe anything on the purchase order. |
| `unordered_items` | noul | Charges for goods or services the purchase order never included. |
| `bank_change_request` | noul | A request to pay a new or changed bank account. |
| `payment_pressure` | noul | Urgent or threatening language pushing to skip the normal approval. |
| `document_kind` | choice | A reminder, credit note or statement sent in as if it were a fresh invoice. |

Vendor invoices also get one generated yes/no question per earlier invoice, asking whether it is the same delivery as invoice X; code builds these at request time from the earlier invoices sent with the request, and only reads the ones dated close enough to the invoice being judged.

## Run it

You need [uv](https://docs.astral.sh/uv/) and a TypeSafe API key.

```sh
cp .env.example .env        # then put your key in .env
uv sync
uv run --env-file .env uvicorn jev_invoices.app:create_app --factory
```

Open http://127.0.0.1:8000/docs to try the endpoints.

Send a sample:

```sh
jq .request samples/expense/taxi.json \
  | curl -s -X POST localhost:8000/expense-invoices -H 'content-type: application/json' -d @- | jq .computed
```

Ask one extra question on a single request, with no code change:

```sh
jq '.request + {extra_questions: {team_event: {type: "noul", instructions: "Is this expense for a team event?"}}}' \
  samples/expense/customer-dinner.json \
  | curl -s -X POST localhost:8000/expense-invoices -H 'content-type: application/json' -d @- | jq .judgments.team_event
```

The answer is stored with the record. No rule reads it until someone writes one.

## What gets stored

Every record goes to `out/invoices.sqlite` and `out/<id>.json`. A record keeps `judgments` (what Jev answered) apart from `computed` (what the code decided), and `jev` holds the model version, latency, input tokens and cost. The price per million tokens is stored next to the cost, because one invoice costs about $0.00004 at roughly 1,000 input tokens, measured with the bench.

## Language bench

```sh
uv run --env-file .env python -m jev_invoices.bench
```

Runs every sample with its Norwegian text and with an English translation, and writes `out/bench.json`. It scores Jev's answers at the app's own thresholds, reports uncertain answers separately from misses, and checks the rules' output (`needs_review`, `saft_code`, `decision`) against each sample's expected result. TypeSafe says English is where Jev is most accurate, so this shows how much Norwegian costs.

## Tests

```sh
uv run pytest                                   # offline, with a fake Jev
uv run --env-file .env pytest -m live -v        # one real call
```

## Limits

- The VAT rules are illustrative and simplified. They are not tax advice. Codes are Skatteetaten's SAF-T standard tax codes.
- The duplicate check only compares against the earlier invoices sent with the request.
- Invoice text is expected to be extracted already. There is no OCR.
- Setting `TYPESAFE_BASE_URL` points the same code at any server that speaks the same API. `cost_usd` always uses Jev's price, so it is only accurate when the server behind that URL is Jev.
