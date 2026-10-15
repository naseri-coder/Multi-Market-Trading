# Stage 21D — Verify RFC 3161 Signed Future-Plan Precommitments

**Research-only cryptographic verifier. No network, TSA subscription, future feed, connected PAPER or real exchange trading.**

Previous Stage21C Draft PR #307 created SHA-256-frozen Brooks V5 future-study plans and purely local hash-chained closed-candle receipts. SHA digests and operator-supplied clock timestamps DO NOT establish independent, pre-study existence.

## New independent-evidence primitive

The new module `naseri_markets/brooks_rfc3161_precommitment_stage21d_v1.py` accepts the original Stage21C exact canonical plan, a DER RFC3161 timestamp response, a certificate of its issuing timestamp signer and the externally operator-approved X.509 trust anchor, each with exact independently approved SHA-256 pins.

It invokes the OS OpenSSL RFC3161 verifier (`openssl ts -verify -data PLAN -in TOKEN -CAfile PINNED_CA -untrusted SIGNER`), which validates the message imprint over the **exact original frozen plan** and timestamp signer certificate chain/EKU. It then extracts the verified token's signed timestamp and requires that it occur **no earlier than** the originally declared plan creation and **no more than one hour after**, and at least 24 hours before the experiment's first future candle. Altered plans, tampered tokens, wrong root certificates, broken certificate chains, a late/backdated registration claim, an ambiguous or missing timestamp, production mode or missing operator acknowledgment fail closed.

No arbitrary shell command can be provided by users; OpenSSL runs with a fixed argument list, bounded input sizes, restricted temporary files, no network or private keys. The temporary files are cleaned up.

## Why an OpenSSL PASS is NOT equivalent to independent approval

The code accepts an operator-selected and SHA-pinned trusted root. A malicious operator can generate a local fake CA and issue a valid-looking timestamp before an invented future study. A *valid RFC3161 signature* establishes **only** that the signed timestamp is consistent with whichever trust anchor the operator supplied. It does NOT independently establish that the TSA is unrelated to the study operator, financially independent, officially accredited or publicly witnessed. Without separate external identity vetting and preapproval of the TSA trust-anchor digest, the verifier always emits:

- `cryptographic_tsa_signature_and_imprint_valid=true`
- `signer_chain_matched_operator_pinned_ca=true`
- `independent_tsa_provider_assessed=false`
- `independent_custody_policy_approved=false`
- `true_prospective_oos_run=false`
- `paper_mode_authorized=false`
- `live_trading_authorized=false`

The unit tests intentionally create their OWN temporary root CA and signer certificate with the critical timeStamping extended key usage and generate actual RFC3161 timestamp tokens via OpenSSL, then verify real PKCS#7 signatures; the tests do not simulate cryptographic verification with mocks. Their local test CA is **not an accepted external witness**. No independently signed user-study plan or genuine future candle has been obtained in this stage.

## Remaining mandatory prerequisites

Before a real future study: separately approve and publish a recognised independent TSA identity and X.509 trust chain SHA pins; create a real frozen Stage21C plan at least 24h before the future window, actually obtain a signed timestamp response, preserve original response bytes, validate independently under the approved trust policy, and collect future venue messages in full with outage/correction evidence. The Stage21C local candle chain alone cannot authenticate original exchange feed signatures.

Additionally, settle Brooks actual execution-order parity, historical contract tiers, exact funding/Mark and real account fees, robust walk-forward research design, and the protected GitHub CodeQL/Publication Safety checks. Do not substitute simulated profitability or market-price hindsight for future OOS. Stage22 and operational Forward/PAPER remain BLOCKED.

All work stays in a Draft PR stacked on Stage21C #307 and its earlier draft dependencies, with no main, Production, account, Telegram or bot alterations.

**Status target:** `STAGE21D_REAL_RFC3161_CRYPTO_VERIFIER_CODE_READY_EXTERNAL_WITNESS_NOT_YET_APPROVED`.
