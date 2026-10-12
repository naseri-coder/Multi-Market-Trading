# Stage 36 — Portable, database-independent offline evidence verification

**Scope: GitHub-only, research/nonproduction. NO designated real host, live service, network probe, Docker/gVisor or trading operation.**

## Why Stage36 exists

Stages 32–35 recorded operator-prepared TEST TLS certificate metadata, independent auditor-signed claims and an unsigned host-local Stage34 self-observation, then linked those statements inside the same owner-private SQLite database. Reviewing an earlier signed record solely through that mutable database left the verifier dependent on the host that stored it. Stage36 introduces a deterministic **portable evidence package** and **independent verifier without any database access**, exposing precisely which claims are authenticated and which still are not.

## Safe exporter

`export_signed_offline_bundle(chain, host_alias=..., sequence=..., operator_ack=True)` reads a single existing Stage35 chain row and its exact referenced Stage33 and Stage32 signed envelopes under a consistent, SQLite read-only snapshot. It emits a bounded, canonical JSON document that embeds exactly four canonical base64 members: original Stage32 signed preparation, Stage33 signed assessment, Stage34 sanitized self-observation and Stage35 signed auditor binding. This operation writes NO new file, sends NO network traffic, does not start or inspect any service, and does not export TLS private keys, database records beyond those four bounded artifacts or other credentials. Operators must treat the archive as internal security metadata, not public media.

## Standalone verifier — no database, no host trust

`verify_signed_offline_bundle(bundle, reviewer_public_key=..., reviewer_key_sha256=..., auditor_public_key=..., auditor_key_sha256=..., expected_host_alias=..., expected_nodename=..., pinned_stage35_sha256=..., pinned_stage35_sequence=..., now=..., operator_ack=True)` verifies in isolation:

1. The caller presents two **distinct** Ed25519 public keys with SHA256 values verified against **independent trustworthy pins**. The verification code never derives trust from keys provided inside the bundle.
2. The bundle must be canonical ASCII JSON, no duplicate or unexpected fields, exactly version 1, bounded length; all four payloads must have exact canonical base64 form and finite bounded bytes.
3. Revalidate all original signature domains: Stage32 reviewer signature for the static local TEST certificate preparation, Stage33 auditor signature over the twelve-category claim report, and Stage35 auditor signature over the self-observation binding. No signing private keys required.
4. Confirm Stage32 restricted nonproduction/static scope, host, certificate SHA256 and TTL, Stage33 status schema and review window, Stage34 raw-byte receipt, TLS cipher, literal false deployment/trading/attestation flags, and Stage35 exact host/nodename/time/sequence and stage32+stage33+stage34 SHA256 references. A matching Stage32/Stage34 TEST certificate SHA is mandatory.
5. Reject expiry or future timestamps, swapped stage records, foreign keys, forged signatures, private-key sign-off masquerading as network evidence, replay against a pinned newer checkpoint, host confusion, noncanonical JSON, oversized body and any claimed installation, trading, Telegram or production permissions.

### The necessary external antirollback anchor

**An unsigned portable bundle cannot establish that it is the newest one.** To prevent a privileged database owner from substituting an old but correctly signed snapshot, the verifier requires an *exact Stage35 signed-binding SHA256 and sequence supplied independently outside the exported bundle and its hosting SQLite database*. The operator must preserve and update that checkpoint in a trusted, independent location (e.g. previously confirmed operator receipt held off-host). Stage36 does **not** create an independent external storage service or claim to have anchored a real deployed machine. If the operator simply copies the purported pin from the untrusted archive, rollback defense is meaningless. This is an exact digest checkpoint, not a global append-only transparency log.

### Strictly bounded conclusion

A passing verifier issues only `INDEPENDENT_SIGNATURE_AND_HASH_CUSTODY_VERIFIED_ONLY`. `original_probe_origin_authenticated`, `actual_host_independently_attested`, `live_firewall_verified`, `gvisor_isolation_certified`, `public_api_deployment_authorized`, `third_party_plugin_execution_authorized`, `telegram_send_authorized`, and `broker_order_authorized` are always **false**. Even a fully valid archive could contain synthetic receipts signed by authorized auditors, because cryptographic signatures authenticate *reviewer statement bytes*, not OS measurements or machine identity.

## CI verification

GitHub Python 3.12 tests use ephemeral reviewer/auditor Ed25519 keys and fully synthetic Stage34 self-observations. They export an actual Stage35 SQLite record, **close the database**, then independently verify the archive. Negative cases cover each tampered member, public-key substitution and key-pin mismatch, duplicate/corrupt/oversized JSON, type confusion, omitted member, swapped host, stale/future evidence, externally pinned sequence or digest mismatch, SQL storage tampering, and explicit production or operator-ack denial. CI also runs the original Stage22–35 tests in source and a clean independently installed wheel and the repository-wide PostgreSQL/publication checks. No actual Linux host evidence is created by these tests.

**Completion criterion: `PORTABLE_OFFLINE_EVIDENCE_CRYPTO_VERIFIED / REAL_HOST_UNDESIGNATED / LIVE_HOST_TEST_NOT_RUN / PUBLIC_DEPLOYMENT_AND_TRADING_BLOCKED`.** No production server, GitHub secret, Telegram, broker account or private NY First-Reversal is modified.
