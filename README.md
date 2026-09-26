# jev-invoices

Companion code for the article "The classifier you don't have to train".

Jev, TypeSafe AI's System One model, answers narrow questions about an invoice. Is it accommodation? Is there alcohol? Does the text announce a new bank account? Plain Python rules turn those answers into a VAT code or an approve, hold or review decision. The model never sees the rules, and the rules never call the model.

## What it shows

- **One request per invoice.** Every question for an invoice goes to Jev in a single request. Jev reads the invoice once and answers all the questions in parallel on its side. Some answers turn out not to matter for a given invoice, and the code simply ignores them.
- **Classifiers defined at runtime.** The questions live in `questions/expense.yaml` and `questions/vendor.yaml`. A new classifier is a new entry there, or an `extra_questions` field on a single request. Vendor invoices also get one generated question per earlier invoice, built from the request data rather than the YAML; expense invoices get one generated choice question per receipt line, built from the lines in the request. Nothing is trained.
- **Policy stays in code.** `src/jev_invoices/rules/` holds the VAT and approval rules as ordinary functions. Each record lists which answers the rules actually read, and only those can send an invoice to review.

## The questions

Each question targets one known expense or accounts-payable problem. Ids are never sent to the model, so each instruction carries the whole question; the rules in `src/jev_invoices/rules/` are the only code that decides on an answer.

### Expense (`questions/expense.yaml`)

| id | type | what it catches |
|---|---|---|
| `hosted_guests` | noul | Customer entertainment (representasjon), whose guests must then be named. A meal with guests gets the same VAT code as any served meal; only the reason differs. |
| `guests_named` | noul | An entertainment claim that does not name who was hosted. |
| `purpose_fits_receipt` | noul | A stated purpose that does not match what was actually bought. |
| `receipt_kind` | choice | A document that is not valid proof of purchase, such as a card slip or a booking confirmation. |
| `purpose_detail` | score | A purpose that is missing or too generic to justify the expense. |

What was bought is not asked at invoice level. Each line in the request gets its own generated choice question, and the rules turn that choice into a VAT code or an effect:

| category | VAT code or effect |
|---|---|
| `lodging` | 13, the low rate |
| `transport` | 13, the low rate |
| `served_food` | 0, no deduction |
| `alcohol` | 0, no deduction |
| `goods` | 1, the regular rate |
| `other_cost` | no code, code it by hand |
| `private_item` | no code, sent to review |
| `unclear` | no code, sent to review |

### Vendor (`questions/vendor.yaml`)

| id | type | what it catches |
|---|---|---|
| `line_specificity` | score | Invoice lines too vague to check against the purchase order, such as "miscellaneous services". |
| `po_items_billed` | noul | Lines that do not describe anything on the purchase order. |
| `unordered_items` | noul | Charges for goods or services the purchase order never included. |
| `bank_change_request` | noul | A request to pay a new or changed bank account. |
| `payment_pressure` | noul | Urgent or threatening language pushing to skip the normal approval. |
| `document_kind` | choice | A reminder, credit note or statement sent in as if it were a fresh invoice. |

Vendor invoices also get one generated yes/no question per earlier invoice, asking whether it is the same delivery as invoice X; code builds these at request time, one only for each earlier invoice dated inside the 60-day resend window.

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

Every record goes to `out/invoices.sqlite` and `out/<id>.json`. A record keeps `judgments` (what Jev answered) apart from `computed` (what the code decided), and `jev` holds the model version, latency, input tokens and cost. The price per million tokens is stored next to the cost, because one invoice costs about $0.00006 at roughly 1,500 input tokens, measured with the bench.

## Language bench

```sh
uv run --env-file .env python -m jev_invoices.bench
```

Runs every sample with its Norwegian text and with an English translation, and writes `out/bench.json`. It scores Jev's answers at the app's own thresholds, reports uncertain answers separately from misses, and checks every value in each sample's expected computed result against the rules' output, not only `needs_review`, `totals_by_code` or `decision`. On the card-slip sample, Jev can infer served food from the shop's name, so that sample's computed values can differ from the literal expectation. TypeSafe says English is where Jev is most accurate, so this shows how much Norwegian costs.

## Tests

```sh
uv run pytest                                   # offline, with a fake Jev
uv run --env-file .env pytest -m live -v        # one real call
```

## Limits

- The VAT rules are illustrative and simplified. They are not tax advice. Codes are Skatteetaten's SAF-T standard tax codes.
- Code only generates a duplicate question for earlier invoices dated inside the 60-day resend window, and a request carries at most 50 earlier invoices.
- Invoice text is expected to be extracted already. There is no OCR.
- Setting `TYPESAFE_BASE_URL` points the same code at any server that speaks the same API. `cost_usd` always uses Jev's price, so it is only accurate when the server behind that URL is Jev.
