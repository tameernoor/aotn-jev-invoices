"""The only module that talks to Jev. Everything else sees plain dicts.

The SDK reads TYPESAFE_API_KEY, TYPESAFE_BASE_URL and TYPESAFE_DEFAULT_MODEL from the
environment and retries rate limits and server errors itself. Pointing TYPESAFE_BASE_URL
at a Jev-compatible local server swaps the model without touching this file.
"""

import time
from dataclasses import dataclass
from typing import Any, Protocol

import typesafe_sdk as ts

PRICE_PER_MTOK_USD = 0.042  # Jev 1.13 input price, docs.typesafe.ai/models, 2026-09-25


class JevRejected(Exception):
    """Jev or the SDK refused the questions. The caller sent something invalid."""


class JevUnavailable(Exception):
    """Jev did not answer, even after the SDK's retries."""


@dataclass
class JevResult:
    judgments: dict[str, dict[str, Any]]
    meta: dict[str, Any]


class AskFn(Protocol):
    async def __call__(self, state: dict, questions: dict[str, dict]) -> JevResult: ...


def _judgment(answer) -> dict[str, Any]:
    if answer.type == "noul":
        return {"type": "noul", "value": answer.noul}
    if answer.type == "choice":
        return {
            "type": "choice",
            "value": answer.choice,
            "probabilities": dict(answer.probabilities),
            "confidence": answer.confidence,
        }
    # The SDK parses score legend/probabilities keys as ints; the wire format and every
    # other consumer of this dict use the string score levels, so normalise back.
    return {
        "type": "score",
        "value": answer.score,
        "probabilities": {str(level): p for level, p in answer.probabilities.items()},
        "confidence": answer.confidence,
        "legend": {str(level): text for level, text in answer.legend.items()},
    }


def _request_id(response) -> str | None:
    try:
        return response.request_id
    except ts.TypeSafeError:  # local Jev-compatible servers may not send the header
        return None


class Jev:
    def __init__(self, client: ts.AsyncTypeSafeClient | None = None):
        self._client = client or ts.AsyncTypeSafeClient()

    async def ask(self, state: dict, questions: dict[str, dict]) -> JevResult:
        started = time.perf_counter()
        try:
            response = await self._client.system_one(state=state, questions=questions)
        except ts.TypeSafeAPIConnectionError as exc:
            raise JevUnavailable(str(exc)) from exc
        except (ts.TypeSafeUnprocessableEntityError, ts.TypeSafeBadRequestError) as exc:
            raise JevRejected(str(exc)) from exc
        except ts.TypeSafeAPIError as exc:
            raise JevUnavailable(str(exc)) from exc
        except ts.TypeSafeError as exc:  # raised by the SDK before sending, e.g. an empty score
            raise JevRejected(str(exc)) from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 1)

        input_tokens = response.usage.input_tokens
        return JevResult(
            judgments={qid: _judgment(answer) for qid, answer in response.answers.items()},
            meta={
                "model": response.model,
                "request_id": _request_id(response),
                "latency_ms": latency_ms,
                "question_count": len(questions),
                "input_tokens": input_tokens,
                "price_per_mtok_usd": PRICE_PER_MTOK_USD,
                "cost_usd": input_tokens * PRICE_PER_MTOK_USD / 1_000_000,
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()
