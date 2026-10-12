# Stage 31 — Hermetic TLS 1.3 verification and offline developer edge hardening

**Nonproduction security acceptance. No server has been provisioned, no socket listener exists, no public API has been launched, and no third-party code is executed.** Stage30 remains an offline ASGI protocol/library. Stage31 strengthens transport security reasoning and the in-process authority boundary, but does **not** replace a security review of a designated disposable HTTPS host.

## 1. Cryptographically verified laboratory TLS handshake

`naseri_markets.tls_boundary_stage31_v1.verify_hermetic_tls_client()` requires an **actual completed Python `ssl.SSLObject` client-side handshake**, not a JSON claim, `scope["scheme"] = "https"` or X-Forwarded-Proto. It verifies that:

- The client context is `ssl.PROTOCOL_TLS_CLIENT`, certificate verification is `ssl.CERT_REQUIRED`, `check_hostname=True`, and its configured minimum protocol is **TLS 1.3**.
- The TLS session really negotiated TLS 1.3 with an approved modern AEAD cipher, and its requested server hostname matches the exact operator-specified DNS name.
- The peer's DER certificate hash matches a **separately supplied exact SHA256 certificate pin**. The configured client trust store must also have accepted the certificate chain during handshake; a weak or unchecked client context is refused.

GitHub acceptance uses `ssl.MemoryBIO` for both client and server and a newly created, ephemeral, self-signed **test-only** key and SAN hostname. Both sides complete a real OpenSSL TLS handshake in memory **without opening a network socket**, then the validator confirms the actual negotiated TLS state and peer certificate pin. Adversarial tests reject an untrusted CA, wrong server hostname, wrong certificate hash, missing hostname verification, context allowing TLS 1.2 as minimum, and unhandshaken/fabricated inputs. Test private key bytes live only in disposable CI scratch files, **never in the source repository or user artifacts**.

The resulting `IN_MEMORY_CLIENT_TLS13_PEER_VERIFIED` receipt is **not** a production TLS check: `public_https_service_tested=false`, `reverse_proxy_trust_independently_verified=false`, `external_host_or_kernel_attested=false`, `public_api_deployment_authorized=false`, `public_plugin_install_authorized=false`. This is stronger than merely testing a mock `https` flag, but is still only a local test of TLS plumbing. See [Python 3.12 SSL documentation](https://docs.python.org/3.12/library/ssl.html) and [OWASP TLS guidance](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).

## 2. Strict HTTP authority guard wrapping Stage30

`StrictDeveloperAuthorityGate(delegate, approved_authority=..., operator_ack=True)` is an **opt-in in-process ASGI wrapper** for the original Stage30 gateway. A future trusted TLS terminator would have to call this wrapper, not the Stage30 application directly.

- Exact approved lowercase DNS `Host` header **required once**, no repeated, differently cased, ambiguous or attacker-controlled authority; ASGI `server=(approved_hostname,443)`, `scheme=https`, HTTP 1.1 or HTTP/2, empty root path and query string.
- Reject percent-encoded or normalized alternate paths, repeated separators, dot segments, backslashes and mismatch between raw HTTP path bytes and the ASGI parsed path. Reject `X-Forwarded-For`, `Forwarded`, `X-Forwarded-Proto`, transfer-encoding smuggling, cookies and any unknown headers via Stage30's already strict header whitelist.
- The wrapper removes only the separately validated Host header, then invokes Stage30's **existing** bounded-body, duplicate-JSON, signed login and token-gated inert ZIP quarantine implementation. Stage29 session is still consumed atomically with Stage28 immutable ZIP receipt and Stage27 permanent public execution prohibition.
- The wrapper repeats the explicit `MMT_NONPRODUCTION=1` fence on **every** request, even when it was constructed earlier.

**Critical trust warning:** ASGI `scope` fields and request headers can be forged by hostile code inside the same Python process; they are not proof of TLS, trusted reverse-proxy custody, certificate identity or client authenticity. The `StrictDeveloperAuthorityGate` verifies HTTP metadata consistency, **not** a real network TLS connection. The separate OpenSSL `MemoryBIO` handshake above is likewise not connected to any deployed ASGI server. Do not call either a successful host penetration test or a real network-layer authorization.

## 3. What is explicitly OUT OF SCOPE

- No cloud/VPS or authorized disposable TLS host was provided. **No** DNS, domain setup, TLS certificate issuance or deployment, ASGI TCP socket, ngrok tunnel, web portal, reverse proxy or public listener was created.
- No production Telegram bot, PostgreSQL, client API credentials, GitHub secrets, external user identities, broker orders, production trade toggles or owner-only NY First-Reversal source was touched.
- No real-host gVisor `runsc` adversarial tests, hostile-code escape tests, independent HSM publisher verification, WAF/DoS attack simulation, certificate rotation/expiry monitoring or operational secret storage exists. No profitability/market feed verification is implied.
- The legacy Stage30 callable remains accessible to trusted local code; Stage31 is an opt-in hardened adapter, not a universal network enforcement fence for future privileged integrations. That must be enforced when an explicitly authorized real host is eventually wired.

## 4. Acceptance and next production prerequisite

Dedicated Stage31 GitHub Python3.12 tests prove a real ephemeral TLS1.3 memory handshake, exact certificate and DNS checks, forged/expired TLS identity refusal, and ASGI Host/path/header spoofing rejections. They also run the Stage22–30 signed-source, isolated-wheel and security regressions, plus full repository PostgreSQL and publication-safety gates before merge.

**Readiness: `LAB_TLS13_VERIFIED / HTTP_AUTHORITY_GUARDED / LIVE_HTTPS_HOST_NOT_TESTED / PUBLIC_DEPLOYMENT_BLOCKED`.**

Next real deployment gate: an independently authorized, credential-free disposable HTTPS test host with true certificate chain, DNS name, per-hop TLS configuration, peer-IP trust and signed deployment provenance, followed by adversarial tests and explicit production authorization. A real deployment is neither requested nor authorized by this stage.
