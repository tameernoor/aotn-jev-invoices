# jev-invoices

Companion code for the article "The classifier you don't have to train".

Jev, TypeSafe AI's System One model, answers narrow questions about an invoice. Is it accommodation? Is there alcohol? Does the text announce a new bank account? Plain Python rules turn those answers into a VAT code or an approve, hold or review decision. The model never sees the rules, and the rules never call the model.

## What it shows

- **One request per invoice.** Every question for an invoice goes to Jev in a single request. Jev reads the invoice once and answers all the questions in parallel on its side. Some answers turn out not to matter for a given invoice, and the code simply ignores them.
- **Classifiers defined at runtime.** The questions live in `questions/expense.yaml` and `questions/vendor.yaml`. A new classifier is a new entry there, or an `extra_questions` field on a single request. Vendor invoices also get one generated question per earlier invoice dated inside the 60-day resend window, built from the request data rather than the YAML; expense invoices get one generated choice question per receipt line, built from the lines in the request. Nothing is trained.
- **Policy stays in code.** `src/jev_invoices/rules/` holds the VAT and approval rules as ordinary functions. Each record lists which answers the rules actually read, and only those can send an invoice to review.

## The questions

Each question targets one known expense or accounts-payable problem. Ids are never sent to the model, so each instruction carries the whole question; the rules in `src/jev_invoices/rules/` are the only code that decides on an answer.

### Expense (`questions/expense.yaml`)

| id | type | what it catches |
|---|---|---|
| `food_for_several` | noul | Food or drink for more than one person, which makes it hospitality. |
| `diners_named` | noul | Hospitality that does not say who ate or drank, required by bokføringsforskriften § 5-10. |
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

Vendor invoices also get generated yes/no questions asking whether this is the same delivery as invoice X. Code builds one for each earlier invoice dated inside the 60-day resend window, at request time.

## What one request looks like

Take `samples/expense/hotel-oslo-minibar.json`: a hotel invoice with two lines, a room and a minibar beer. One request goes to Jev with the receipt text, the countries and the stated purpose as `state`, and seven questions:

| # | id | type | asks, in short |
|---|---|---|---|
| 1 | `food_for_several` | noul | Does the invoice show food or drink for more than one person? |
| 2 | `diners_named` | noul | Does the purpose say who ate or drank, by name, company or group? |
| 3 | `purpose_fits_receipt` | noul | Do most of the lines fit the stated purpose? |
| 4 | `receipt_kind` | choice | Proof of purchase, card slip, booking confirmation or other? |
| 5 | `purpose_detail` | score | How specific is the purpose? |
| 6 | `line_1` | choice | What kind of purchase is "Overnatting enkeltrom, 2 netter"? |
| 7 | `line_2` | choice | What kind of purchase is "Minibar: Pils 0,33 l"? |

Jev answered them together in about 0.3 seconds. The rules then coded the room 13 and the beer 0 (alcohol, no deduction), with totals of 2,900.00 and 89.00. `diners_named` was answered but never read, because the minibar beer was food or drink for one person, not several.

Questions 1 to 5 are the same for every expense invoice. The line questions follow the receipt, so a taxi receipt with one line sends six questions and a dinner with three lines sends eight. A vendor invoice sends six fixed questions plus one duplicate question per recent earlier invoice.

## Measured

All numbers are against `jev-1.13.0`.

### On the 16 samples (tuning set)

The questions were rewritten over several rounds against these same 16 samples until they passed, so these numbers show that the questions fit the samples they were tuned on. They are not evidence of accuracy.

- 108 to 109 of 112 answers on the right side of the app's thresholds, none on the wrong side.
- The rules produced every sample's expected result in English, and 15 of 16 in Norwegian.

### On 20 held-out documents

`samples/holdout/` holds 12 receipts and 8 supplier invoices written afterwards by a separate author. They were committed before the first run, and the questions were not changed after it. They were run once, in Norwegian and in English (`python -m jev_invoices.bench samples/holdout`).

- 136 to 137 of 143 answers on the right side of the thresholds, 5 uncertain, and 1 to 2 on the wrong side.
- The rules produced the expected result for 16 of 20 documents in English and 14 of 20 in Norwegian.
- Of the 10 wrong outcomes, 9 sent a document to review that should have passed. Most were caused by uncertain answers near a threshold: six beers read as maybe more than one person (in English 0.80, just enough to count as yes, together with a purpose read as too generic; these are the two wrong-side answers), a hotel dinner in Paris read as maybe for more than one person, "the department" read as maybe not naming who ate, a freight line read as maybe not ordered, and "equipment for the home office" read as maybe too generic a purpose.
- One went the other way. In Norwegian, a lip balm on a pharmacy receipt was classified as goods with 0.62 confidence, just above the 0.6 needed for a choice to count, so the private item was not flagged. In English the same line was 0.58, just under, and went to review.

### Speed and cost

These numbers measure throughput, not correctness.

- 0.23 to 0.41 seconds per document (mean about 0.3), almost all of it the Jev call.
- About 1,000 to 2,600 input tokens per document, which is $0.00004 to $0.00011 at Jev's input price.
- 1,000 receipts sent to the local API with 20 requests in flight took 17.4 seconds, about 57 per second, with no errors. Median call 0.28 seconds, 90 % under 0.32 seconds. One call took 10.7 seconds, most likely a retry inside the SDK. 1.8 million input tokens in total, $0.076.

TypeSafe's published rate limits (1,200 requests a minute, 250,000 tokens a second, currently adjusted dynamically) set the ceiling for larger batches.

## Run it

You need [uv](https://docs.astral.sh/uv/) and a TypeSafe API key.

```sh
cp .env.example .env        # then put your key in .env
uv sync
uv run --env-file .env uvicorn jev_invoices.app:create_app --factory
```

Open http://127.0.0.1:8000/docs to try the endpoints.

An expense request carries its receipt lines as data:

```json
{
  "invoice_text": "...",
  "lines": [{"text": "Tur: Oslo lufthavn – Majorstuen", "amount": "845.00"}],
  "employee_country": "NO",
  "vendor_country": "NO",
  "expense_purpose": "Hjemreise fra konferanse"
}
```

The lines arrive already extracted, the way a receipt scanner delivers them, and each amount is the line's total, not a unit price. If `lines` is left out, the invoice goes to review with "The receipt lists nothing that was bought."

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

Every record goes to `out/invoices.sqlite` and `out/<id>.json`. A record keeps `judgments` (what Jev answered) apart from `computed` (what the code decided), and `jev` holds the model version, latency, input tokens and cost. The price per million tokens is stored next to the cost, so the cost can be checked later; one invoice costs a small fraction of a cent (see Measured).

## Language bench

```sh
uv run --env-file .env python -m jev_invoices.bench
```

Runs every sample with its Norwegian text and with an English translation, and writes `out/bench.json`. It scores Jev's answers at the app's own thresholds, reports uncertain answers separately from misses, and checks every value in each sample's expected computed result against the rules' output, not only `needs_review`, `totals_by_code` or `decision`; when comparing, line text is ignored, so the English run is judged on category, amount and code. TypeSafe says English is where Jev is most accurate, so this shows how much Norwegian costs. Pass an optional samples folder, e.g. `uv run --env-file .env python -m jev_invoices.bench samples/holdout`, to bench only that folder's `expense` and `vendor` samples and write to `out/bench-<folder name>.json` instead.

## Tests

```sh
uv run pytest                                   # offline, with a fake Jev
uv run --env-file .env pytest -m live -v        # one real call
```

## Limits

- The VAT rules are illustrative and simplified. They are not tax advice. Codes are Skatteetaten's SAF-T standard tax codes.
- Code only generates a duplicate question for earlier invoices dated inside the 60-day resend window, and a request carries at most 50 earlier invoices.
- Invoice text and receipt lines are expected to arrive already extracted. There is no OCR.
- Amounts are summed as given; there is no currency conversion.
- A foreign vendor codes every line 0 (no Norwegian deduction).
- Setting `TYPESAFE_BASE_URL` points the same code at any server that speaks the same API. `cost_usd` always uses Jev's price, so it is only accurate when the server behind that URL is Jev.
