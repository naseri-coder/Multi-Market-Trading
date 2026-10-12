# Stage 30 — Nonproduction ASGI developer API contract for signed quarantine

**GitHub-only, no listener.** Stage30 creates an in-process ASGI HTTP application, not a website or publicly routable API. No ASGI server, reverse proxy, DNS, TLS certificate, socket or production service is provisioned or run. It is deliberately unavailable to developers over the internet until the operator independently approves a complete transport and threat-model review.

## Controlled endpoints

| Method | Path | Response / authorization |
|---|---|---|
| POST | `/v1/developers/challenge` | Stage29 short-lived challenge, only for pre-enrolled ACTIVE Stage28 publisher key |
| POST | `/v1/developers/session` | Check exact Ed25519 challenge signature and return a 5-minute **one-use** bearer token |
| GET | `/v1/developers/me` | Limited status of the currently authenticated publisher, no key material |
| POST | `/v1/developers/logout` | Revoke the token; body exactly `{}` |
| POST | `/v1/developers/quarantine` | Bind token to exact operator-selected Stage23 candidate; append an inert ZIP to Stage28/Stage27 owner-private quarantine |

The challenge body is exactly `{"tenant_id":"...","publisher":"...","key_id":"..."}`. The signature body is exactly `{"challenge":{...},"signature_b64":"<canonical standard base64>"}`. The upload body is exactly `{"binding_id":"...","package_b64":"<canonical standard base64 ZIP>","candidate_b64":"<canonical base64 Stage23 dual-signed claim>"}`. The authorization is **only** the `Authorization: Bearer <one-time-token>` header; do not send credentials in URLs or upload JSON. No uploaded JSON can specify core manifest, host image, tenant ID, publisher ID, account, trading settings, position, exchange credentials or runtime permissions. A separately trusted operator binds the `binding_id` to a static `ReviewedUploadTarget` with its approved CoreManifest, CoreBinding, independently pinned OCI image and Stage23 signing witness.

On success, the route replies **202 QUARANTINED_PUBLIC_SOURCE_NOT_EXECUTABLE** with a package SHA256 and explicitly false install, execution, Telegram and brokerage authorization. Stage29 consumes the bearer and Stage28 + Stage27 atomically register the permanently blocked public candidate in the same Stage22 SQLite transaction. Auth failures, key revocation, expiry, repeat submits, wrong signer, source changes or signature tampering all fail closed.

## Input and abuse controls

- Exact method and path; no query parameters, cookies, forwarded headers, unknown request headers or override methods. Strict JSON object field sets, duplicate-key rejection, non-finite JSON denial, ASCII-only canonical signature encoding, base64 validation and no client-controlled code loaders
- No compressed HTTP body, chunked transfer-header interpretation, smuggled Content-Length, duplicated headers, or forged `X-Forwarded-For`. ASGI receive chunks are bounded to **32**, total body **132,000 bytes**, and auth requests to **8,192 bytes**; ZIP decode remains bounded to Stage28's 90,000 byte, two-file STORED-only archive with SHA verification
- Persistent per trusted **ASGI peer IP** rate bucket of at most **12 requests per minute**, overall max **256 active peer buckets per minute**, with rate-accounting under SQLite `BEGIN IMMEDIATE`; Stage29 additionally enforces its per-publisher pending challenge and session quotas
- No bearer echo in errors or user-facing logs, no cookies and no caching: `Cache-Control: no-store`, `Pragma: no-cache`, `X-Content-Type-Options: nosniff`, restrictive CSP and HSTS in response
- Refuse missing `https` ASGI scheme and missing/malformed peer IP supplied by a trusted ASGI host. **IMPORTANT: the scheme/client ASGI fields are NOT cryptographic proof of TLS**. A future reverse-proxy deployment must actually terminate verified TLS, authenticate and constrain forwarding, enforce client IP identity under its trust boundary, and perform independent infrastructure security testing. The in-process app should never be handed arbitrary forged `scope` objects by external callers
- No installer, source import, gVisor invocation, public strategy marketplace activation, broker order or Telegram send endpoints. No generic `/admin`, `/run`, `/execute`, `/download` or `/trade` routes

## Operator integration (conceptual; NOT a deployment command)

A trusted nonproduction operator must first open the already reviewed Stage22 ledger, Stage28 publisher registry, Stage29 authenticated intake and Stage23 witness with exact pinned public keys. A `ReviewedUploadTarget(manifest, binding, signed_witness, pinned_image)` is constructed ONLY from operator-reviewed data. Then create `OfflineDeveloperAsgiGateway(intake, reviewed_targets={binding.binding_id: target}, operator_ack=True)` on the same owner-private offline host, while `MMT_NONPRODUCTION=1` and `MMT_PRODUCTION` is unset. A test ASGI caller can invoke the `app(scope, receive, send)` coroutine directly with a synthetic **HTTPS** scope. **Do not start uvicorn, hypercorn, gunicorn, expose an HTTP port, or attach it to production** as part of Stage30.

The new API does not replace the operator's Stage28 key-enrollment control, the Stage23/24 independently reviewed signer and host-observation custody, the Stage26/27 permanent execution denial, or the Stage29 one-time session enforcement. The preexisting trusted nonproduction research path still remains separately available, which means this module is **not** proof that every conceivable malicious privileged host path is fenced.

## Automated verification and hard limitations

The GitHub Actions acceptance runs the Stage30 ASGI coroutine **entirely in memory**, no external socket or internet. It uses real ephemeral Ed25519 keys for registered publisher challenge signing and Stage23 candidate signing, and tests arbitrary incorrect headers, duplicate JSON, source/claim/base64 tampering, replay, logged out/expired/revoked sessions, direct legacy bypass, wrong target and rate limits, error confidentiality, and one-shot Stage27/28 quarantine. Stage22–29 targeted regressions, an independent installed-wheel acceptance suite, full repository regression with PostgreSQL and publication-safety workflow all remain required before merge.

The endpoint is a **protocol/library preview** rather than a deployed and independently penetration-tested public web service. A real developer platform requires network-layer TLS, reverse-proxy trust, client/session tracking, abuse-monitoring, defense against distributed botnets, alerting, independent adversarial validation of Docker/gVisor, real identity onboarding and signer custody. No historical market outcome or profitability is proven. Owner-only NY First-Reversal stays private and no production changes are authorized.

**Readiness verdict: `OFFLINE_ASGI_QUARANTINE_CONTRACT_ONLY / PUBLIC_DEPLOY_AND_EXECUTION_BLOCKED`.**
