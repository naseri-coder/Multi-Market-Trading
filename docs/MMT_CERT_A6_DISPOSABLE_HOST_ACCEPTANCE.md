# CERT-A6 — disposable-host gVisor containment acceptance preparation

**State: CODE/POLICY PREPARED; REAL HOST NOT DESIGNATED; NO ATTESTATION.**

CERT-A5 proved that the existing A2 benign fixtures actually run in Python,
JavaScript, TypeScript and Wasmtime against causal replay events. It did not
show that hostile or externally submitted code is safely contained. CERT-A6
does NOT change the existing A1/A3/A6 Worker dispatch authorization.

## Real environmental blocker

No independently designated expendable Linux host is assigned to this stage.
Existing TELMIVO, TELMIVO License Authority and trading hosts are prohibited.
Do NOT reinterpret a generic GitHub Actions runner as independent rootless +
gVisor host certification. There is also no independently attested immutable
four-language OCI image and verified dependency/signer custody in the repo.

Consequently: the host execution tests **have NOT RUN**, and a successful
mock unit test must never be reported as sandbox certification.

## Implemented

- naseri_markets/cert_a6_disposable_containment.py is an *opt-in host-only*
  fixed benign probing tool for a future approved disposable host.
- The tool calls the existing **real** RUNTIME-A7 preflight first. A7
  establishes a non-root invoking user, private rootless Docker socket,
  SHA-pinned runsc binary, runtime registration, and locally available exact
  digest-addressed image. An SHA-pin does not prove publisher identity.
- Only after an explicit second opt-in, the tool may invoke one fixed, literal
  Python probe (NOT untrusted strategy source) in that digest-addressed
  image, with --pull=never, --runtime=runsc, --network=none, --ipc=none,
  --read-only, --cap-drop=ALL, no-new-privileges, non-root UID 65534,
  fixed memory/CPU/PID limits, no bind mounts and small writable tmpfs.
- The fixed probe tests non-root execution, a refused write at filesystem
  root, a refused TCP connection to TEST-NET address 203.0.113.1, and the
  absence of a few named credential variables. These are narrow observations;
  they do NOT rule out untested network paths, environment exposures,
  sandbox escape, metadata channels, resource exhaustion or compromised host.
- After any attempt, the tool requests exact-container removal, checks daemon
  liveness and absence of the generated container name. These observations
  are NOT independent process orphan proof.
- Result is a small aggregate non-authorizing report; no trading data,
  credential value or Worker source bytes are sent or stored.
- The GitHub Actions workflow runs **mock-only** checks, including negative
  environment, malformed probe, timeout, forged fields, missing A7 approval,
  failed cleanup and existing A6 denial. It NEVER runs Docker.

## Future operator-only command — DO NOT RUN before host designation

Only after an operator designates and reviews an expendable, no-secrets,
nonproduction host **separate from all attached production environments**,
reviews the exact tool and image sources, and supplies a real independently
verified runsc hash and Worker image digest:

    MMT_NONPRODUCTION=1 \
    MMT_CERT_A6_DISPOSABLE_HOST_APPROVED=1 \
    python -m naseri_markets.cert_a6_disposable_containment \
      --host-id YOUR_DESIGNATED_DISPOSABLE_HOST_ID \
      --image YOUR_VERIFIED_REPOSITORY@sha256:YOUR_64_HEX_DIGEST \
      --runsc /ABSOLUTE/REVIEWED/RUNSC/PATH \
      --runsc-sha256 YOUR_REAL_INDEPENDENT_64_HEX_DIGEST \
      --ack-disposable-host

The placeholders are intentionally NOT runnable. Do NOT infer a valid image
digest, copy an example hash, pull or rebuild an image on a production host,
or bypass checks by monkeypatching A7 or RUNTIME-A6.

## Explicit remaining acceptance work

1. Identify owner, scope and lifecycle of a dedicated isolated throwaway host.
   Confirm it contains NO broker/Telegram/SSH/DB production secrets and no
   reachable management control plane. Protect host network upstream.
2. Independently reproduce and verify all OCI layer/toolchain hashes,
   upstream package provenance, trusted signer, revoked-key handling and
   immutable image custody. A2 Dockerfile still relies on mutable inputs.
3. Execute the **real** passive A7 probe on that host, then the fixed A6
   containment probe. Record independent runsc selection and time/host/image
   measurements; reproducibly retain redacted results out-of-band.
4. Add isolated **real four-language Worker E2E** inside that runsc sandbox,
   not just Python host probes; exercise bounded network/FS, timeouts,
   CPU/memory/PIDs, crashes, restart, container orphan cleanup, compromised
   inputs, revoked image and credential denial. No untrusted code until
   the host containment acceptance has passed.
5. Independent human review and authorized next release gate; maintain A6
   unconditional rejection and all order/publisher permissions denied.

## Current verdict

CERT_A6_SOURCE_PREPARED_HOST_REQUIRED_NO_EXECUTION_CERTIFICATION

All runtime-a6 Worker dispatch and quarantine-release permissions remain
DENY. No real host test, production deploy, broker order, signal/Telegram
publication, or source strategy mutation is part of this stage.
