# Stage 34 — Explicitly designated disposable host, read-only local probe

**Deployment status: BLOCKED. No real host designated or probed in this stage.** This change delivers a concrete operator-invoked Linux probe for use **only after separately designating and authorizing a disposable, non-root, credential-free host**. It is not a cloud-provisioning script, daemon, public endpoint, trading feature, Docker job, gVisor certification or server migration.

## What the probe actually measures on a designated host

`naseri_markets.designated_host_readonly_probe_stage34_v1.probe_designated_local_host()` requires `MMT_NONPRODUCTION=1`, `MMT_DISPOSABLE_SANDBOX_HOST=1`, no `MMT_PRODUCTION=1`, explicit operator acknowledgement, non-root Unix effective UID and an exact host `os.uname().nodename` match. The caller must separately identify and authorize that host **out of band**. These environment variables and the hostname are only accidental-misuse guards; an attacker able to change them is not authenticated by this interface.

It then reads **only** `/proc/net/tcp` and `/proc/net/tcp6` with strict bounds, parses Linux LISTEN rows, rejects wildcard (`0.0.0.0`, `::`) and non-loopback TCP listeners, and requires an already existing `127.0.0.1:443` listener. It **never** opens a listening port, installs firewall rules or assumes listener discovery proves ingress filtering. A listener can change immediately after the read. Existing SSH/outbound firewall routes and UDP exposure are not covered by the TCP snapshot.

Next, it reads only an owner-private, separately provided **public test CA** file; `Stage32._private_file` requires a private directory and a 0600 regular file. No TLS private key is read, generated or exported. It opens a TLS1.3 client socket to exactly **127.0.0.1:443** with a separately pinned test hostname ending in `.test` or `.invalid`. It enforces CA trust verification, SNI hostname matching, TLS1.3-only negotiation, modern TLS cipher and an independently supplied SHA256 pin of the peer DER certificate. There is no external network connection or real public-CA/DNS verification. The loopback TLS listener must be separately created by the authorized operator; Stage34 does **not** create it or start the Stage30 API.

The returned `HostLocalProbeReceipt` contains only safe metadata: host alias and nodename, observation timestamp, **hash** of the two kernel TCP snapshots, count of local listeners, peer certificate SHA256 and negotiated cipher. The canonical JSON serialization and its SHA256 are suitable for manual Stage33 evidence custody **after** independent review. No cert private keys, CA bytes, environment variables, credentials or process command line are serialized. The status is deliberately `ON_HOST_SELF_OBSERVATION_NOT_INDEPENDENT_ATTESTATION`.

## Explicitly NOT verified

- Host custody is only checked against caller-supplied nodename and environment flags. **No independent identity attestation** (TPM, measured boot, remote verifier, approved host allowlist service).
- The passive local TCP snapshot and TLS handshake do not prove inbound **firewall policy**, egress blocking, UDP exposure, reverse proxy configuration, server-to-server TLS, public cert issuance or DNS.
- No Docker socket use, gVisor/runtime introspection, rootless resource/cgroup verification, hostile source escape tests or plugin imports. Stage23's independent fixed canary remains separate and opt-in only on an approved real host.
- A compromised local OS can fabricate its own `/proc` data and loopback certificate. The owner must separately verify custody, signatures and hashes; Stage33 independent reviewer claims do not automatically transform local observations into independent measurements.
- Real deployment, public installation, Telegram publication and broker orders remain **false** even when all of these self-observations pass.

## Manual, host-only invocation (NOT authorized by CI)

After the operator separately designates a credential-free, independently isolated Linux test host and already has a loopback-only port 443 TLS1.3 test service with exact pinned SAN + CA, the operator can opt in:

```sh
MMT_NONPRODUCTION=1 MMT_DISPOSABLE_SANDBOX_HOST=1 \
python -m naseri_markets.designated_host_readonly_probe_cli_stage34_v1 \
  --host-alias <approved_disposable_alias> \
  --expected-nodename <exact_uname_nodename> \
  --tls-hostname developers.staging.invalid \
  --certificate-ca-file /operator-private/test-ca.pem \
  --certificate-der-sha256 <64_hex_digits_from_independent_review> \
  --ack-disposable-readonly-probe
```

The example is **documentation for a separately approved future host**, not a command run against any existing server. CLI emits only canonical JSON to stdout on success and a generic refusal to stderr on failure, with exit code 2. It writes no files and does not manage the actual test TLS server. Do not run on the project's live bot, database, licensed infrastructure, user accounts or any host not separately designated. Do not redirect its output to public logs.

## Tests and readiness

The GitHub CI tests `/proc/net/tcp{,6}` parsing against synthetic deterministic snapshots, root/nonproduction/hostname/port/loopback refusals, strict and bounded errors, and an **actual OpenSSL TLS1.3 handshake over a local socketpair** using ephemeral certificates. It does **not** run the host-bound probe against the GitHub runner or open a public server. The suite also tests Stage22–33 contracts, independent installed wheel, PostgreSQL and publication safety gates.

**Readiness after CI: `MANUAL_HOST_READONLY_PROBE_READY / REAL_HOST_NOT_DESIGNATED / LIVE_HOST_TEST_NOT_RUN / GVISOR_UNTESTED / PUBLIC_DEPLOYMENT_BLOCKED`.**

The next genuine acceptance step cannot proceed without explicitly identifying a disposable host and separately authorizing the precise operations. No such authorization is supplied by a generic request to continue development.
