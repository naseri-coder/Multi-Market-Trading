# Stage 33 — Disconnected host-assessment claims intake (no host available)

**AUTHORIZED SCOPE: OFFLINE/NONPRODUCTION GITHUB RESEARCH.** No standalone disposable host is designated or connected. Stage33 builds a controlled **evidence review intake**, NOT a network probe, remote-attestation system, security certification, public API or host deployment. The real-host verification verdict remains **NOT_RUN / BLOCKED**.

## Why

Stage32 created a narrow signed record of locally reviewed **test** TLS files and a **proposed** network posture. Neither is proof of the firewall, live TLS certificate chain, reverse proxy, gVisor confinement or secrets on a real host. Stage33 defines the precise claims that a separately authorized operator and independent auditor will need to review, while refusing to infer any live readiness from paper evidence alone.

## Mandatory independent assessment checklist

`host_assessment_checklist()` publishes twelve stable checks covering: custody of the designated disposable host; OS/runtime provenance; actual TLS1.3 handshake to a real endpoint; live certificate chain, DNS hostname and expiry; private key and secret permissions; ingress firewall limited to loopback; outbound network-deny; reverse proxy peer/IP/header trust; absence of broker and Telegram credentials; gVisor and cgroup limits; adversarial escape-negative tests; and log redaction plus evidence integrity.

For each check, the **untrusted reviewer report** may say `NOT_RUN`, `DECLARED_PASS` or `DECLARED_FAIL`; non-UNRUN statuses require a valid SHA256 evidence pointer. These are declared results and hashes, **not proof of measurements**. An attacker able to control the host and the files can fabricate both a claim and a hash. Stage33 explicitly NEVER emits `HOST_VERIFIED`, even if all twelve checks are `DECLARED_PASS`.

## Signed custody linked to Stage32

`DisconnectedHostEvidenceLedger` uses the owner-private Stage32 SQLite dossier. It requires the previously pinned Stage32 preparation reviewer's Ed25519 public key and a **different** independently pinned Stage33 auditor public key; the keys cannot coincide. A signed, canonical and size-bounded report references the **exact previously recorded Stage32 signed statement SHA256** and includes host alias, short validity period (up to one hour), monotonically increasing sequence number, all checklist statuses and digests, and explicit false declarations for public deployment, plugin installation, strategy execution, Telegram sends and broker orders.

Before accepting a report, Stage33 checks the Stage32 stored signed statement **again** with its original reviewer key, matching database digests, alias and expiry. It verifies the additional Stage33 auditor Ed25519 signature with domain separation, exact JSON field sets, canonical encoding, no duplicate keys and no replay or sequence gaps. An append-only SQLite table, immutable triggers and an independently pinned auditor key preserve local evidence custody across process restarts. This protects against accidental database API edits and signed-packet replay; it **does not** protect against a privileged database/filesystem owner deleting or replacing the entire evidence store, signer private-key compromise, or fabricated real-world host assertions. No trusted private signing key is created, stored or released by this module.

## Status is always fail-closed

`DisconnectedHostReviewReceipt` reports the number of **declared** checks passed, failed or not run. Its fields `actual_host_independently_verified`, `actual_tls_endpoint_verified`, `network_policy_enforced`, `gvisor_isolation_certified`, `public_ingress_authorized`, `public_installer_authorized`, `telegram_send_authorized` and `broker_order_authorized` are **always false**. This is an information and custody interface, not an installer or trading permission.

The unsigned `status(host_alias)` returns a safe row count and latest sequence, still showing live TLS, firewall, gVisor, independent host attestation and public deployment as false. If no host has been designated, record count is zero and there is no live result.

## Future host prerequisites (not part of Stage33)

A later, separately authorized stage must explicitly designate an isolated disposable host with no production credentials and permit limited **read-only** host inspection. It should verify real TLS with the independent pinned DNS authority and certificate chain, firewall/network rules, reverse proxy trust, non-root process identity, private key storage, ephemeral test traffic, gVisor/cgroup behavior and negative malicious-source tests **without involving production users**. Collect evidence using a custody-verified mechanism and independent auditor. Even that future host review does not by itself authorize public plugin installation, source execution, trading or deployment; these remain separate risk decisions.

**Stage33 result after passing GitHub CI: `SIGNED_OFFLINE_CLAIMS_CUSTODY_READY / DESIGNATED_HOST_NOT_PROVIDED / ACTUAL_HOST_TEST_NOT_RUN / PUBLIC_INSTALL_BLOCKED`.**

No production host, BotFather configuration, Telegram channel, production PostgreSQL DB, broker API, deployment, Docker daemon or the private NY First-Reversal strategy is changed.
