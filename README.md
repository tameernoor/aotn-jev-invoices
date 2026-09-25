# jev-invoices

Companion code for the article "The classifier you don't have to train".

Jev, TypeSafe AI's System One model, answers narrow questions about an invoice. Is it accommodation? Is there alcohol? Does the text announce a new bank account? Plain Python rules turn those answers into a VAT code or an approve, hold or review decision. The model never sees the rules, and the rules never call the model.

## What it shows

- **One request per invoice.** Every question for an invoice goes to Jev in a single request. Jev reads the invoice once and answers all the questions in parallel on its side. Some answers turn out not to matter for a given invoice, and the code simply ignores them.
- **Classifiers defined at runtime.** The questions live in `questions/expense.yaml` and `questions/vendor.yaml`. A new classifier is a new entry there, or an `extra_questions` field on a single request. Nothing is trained.
- **Policy stays in code.** `src/jev_invoices/rules/` holds the VAT and approval rules as ordinary functions. Each record lists which answers the rules actually read, and only those can send an invoice to review.

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

Every record goes to `out/invoices.sqlite` and `out/<id>.json`. A record keeps `judgments` (what Jev answered) apart from `computed` (what the code decided), and `jev` holds the model version, request time, input tokens and cost. The price per million tokens is stored next to the cost, because one invoice costs around a hundredth of a cent.

## Language bench

```sh
uv run --env-file .env python -m jev_invoices.bench
```

Runs every sample with its Norwegian text and with an English translation, compares Jev's answers with the expected ones, and writes `out/bench.json`. TypeSafe says English is where Jev is most accurate, so this shows how much Norwegian costs.

## Tests

```sh
uv run pytest                                   # offline, with a fake Jev
uv run --env-file .env pytest -m live -v        # one real call
```

## Limits

- The VAT rules are illustrative and simplified. They are not tax advice. Codes are Skatteetaten's SAF-T standard tax codes.
- The duplicate check only compares against the earlier invoices sent with the request.
- Invoice text is expected to be extracted already. There is no OCR.
- Setting `TYPESAFE_BASE_URL` points the same code at any server that speaks the same API.
