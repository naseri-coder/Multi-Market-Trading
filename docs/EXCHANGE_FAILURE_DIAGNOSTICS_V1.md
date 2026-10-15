# Exchange Failure Diagnostics V1 — nonproduction

**Scope:** Independent, additive, diagnostic-only code. No live connector is enabled. No transaction is created, retried, cancelled or reconciled by this module. No original error text is stored. Existing dispatch, publication, broker authorization, residency restrictions, risk, database, private cores and deployment remain unchanged.

## Purpose

The module `naseri_markets.exchange_failure_diagnostics_v1` accepts host-supplied error **evidence** from a venue and emits a frozen `FailureDiagnosis` with a normalized venue, stable category, **human action hint**, and non-sensitive reason tag. It contains **no automatic retry flag or trading permission**.

- Exact structured exchange-code matches are scoped to the declared venue. Cross-venue numeric coincidences do not match. Supported codes are intentionally narrow and must be expanded only after provider-authenticated test fixtures are reviewed.
- HTTP 401/403 access failures, 429 rate limits, and 5xx server failures take precedence over message-based guesses. For `request_submitted=True` (default), a server/transport failure is **ambiguous**: `reconcile_before_any_retry`. Only an independently proven pre-dispatch failure may be tagged as `request_submitted=False`.
- Message-based matches are weaker hints than structured matches. Unrecognized or malformed evidence is `unclassified` / `stop_and_review`, never an inferred approval.
- No original message, exchange code, URL, token, response body or raw exception is included in the returned dataclass or logs. Inputs are bounded; messages over 2048 characters are not parsed.
- The action `wait_and_inspect` is **human guidance**, not permission for a service to repeat an order. The real order execution path must make an independent authorization/reconciliation decision.

## Usage (inert example)

```python
from naseri_markets.exchange_failure_diagnostics_v1 import diagnose_exchange_failure

finding = diagnose_exchange_failure(venue="binance", http_status=503, request_submitted=True)
assert finding.action == "reconcile_before_any_retry"
assert finding.evidence == "HTTP_SERVER_FAILURE"

```


## Provider references and classification corrections

The deliberately small mapping was checked against official reference material, with mismatches corrected before this PR: Bybit `110017` is quantity truncation, not a position conflict; Binance `-1013` is a generic invalid-message code and is intentionally left unclassified. HTTP 403 can indicate WAF, regional or other access restrictions, not necessarily a bad API key. Code `40018` indicates an invalid IP in the Bitget API catalog.

- [Binance USD-M error codes](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/error-code)
- [Bybit V5 error codes](https://bybit-exchange.github.io/docs/v5/error)
- [OKX API reference](https://www.okx.com/docs-v5/en/)
- [Bitget error codes](https://www.bitget.com/docs/uta/error-code/restapi)

Structured codes and endpoint/market variants still require independent test fixtures before live integration.

## Acceptance and open limitations

The unit corpus exercises exact venue separation, secret non-disclosure, malformed/oversized evidence, conflicting HTTP and venue codes, transport ambiguity, action immutability and pre-dispatch distinctions. No real exchange API, account, database, telemetry service or broker is contacted. The classifier is **not an official vendor error-code catalog**, and inferred messages are not evidence of actual order acceptance or failure.

This stage intentionally has **no runtime wiring**: subsequent adoption in a live adapter requires separate explicit authorization, test fixtures from each provider, validated precision and order-reconciliation semantics, and security review.
