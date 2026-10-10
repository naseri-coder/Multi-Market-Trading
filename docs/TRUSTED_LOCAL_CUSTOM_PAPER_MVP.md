# Multi Market Trading — Trusted Local Custom Engine PAPER MVP

**Product capability, not another A-series. Status: usable OFFLINE development workflow only.**

This feature now executes **a real, locally supplied public Custom Python
engine**, with an explicit operator trust decision. It is NOT A23's inert
echo-only sandbox, not A25's ZIP fixture, and is not an open marketplace.
It runs via `python -I -S` in a child process with a bounded timeout. It is
**not an adversarial sandbox**: the trusted child retains the invoking user's
OS filesystem/network privileges. Only run code you independently reviewed.

## Five completed capability boundaries

1. **Shared contract:** Existing A21 `public_custom/generic_custom`
   descriptor (metadata-only SHA-256 approval), new executable worker
   protocol input `{"abi_version":1,"engine_id":...,"engine_version":...,
   "tick":{...}}`, output `{"status":"no_signal"}` OR the exact
   validated **A7 PAPER envelope**. Worker must be a single standalone,
   UTF-8, Python 3.12 script using the standard library in this MVP.
   No dynamic plug-in import into the bot process.
2. **Explicit trusted-local registration:** Operator independently pins
   descriptor bytes and Python source bytes, supplies both hashes, and
   explicitly confirms `--trust-local-code`. Host copies approved bytes
   into an OS-private `0700` state directory as a `0600` snapshot.
   The descriptor alone never grants execution, nor do A24/A25 inert
   metadata admissions. No download, encrypted package, binary installer
   or third-party publisher authentication.
3. **Default disabled + persistent controls:** SQLite engine registry stores
   version, hashes, disabled/enabled flag and monotonic revision. Explicit
   `enable` needs approved manifest digest AND current revision. `disable`
   also uses CAS and increments revision.
4. **Actual PAPER processing:** Load strict synthetic/replay Bid/Ask quote.
   Reject LIVE input. Verify A21 market/version, byte-identical source
   snapshot, exact worker JSON envelope, A7 causal timestamp, nonnegative
   geometry, identity, and PAPER mode. Timeout, nonzero exit or malformed
   outputs are **quarantined** by disabling the engine. Store canonical
   A7-shaped PAPER signals and plugin enable state in **one SQLite file**;
   final enabled/revision check and signal insert use the **same BEGIN
   IMMEDIATE transaction**. Exact signal ID replay is idempotent; altered
   payload on same ID rolls back. Neither broker nor Telegram is called.
5. **Usable installed CLI:** `naseri-custom` installed in the isolated
   `multi-market-trading==0.4.0rc1` wheel, plus `python -m
   naseri_markets.custom_cli`. Command set: `sample`, `register`,
   `list`, `enable`, `disable`, `paper`, `signals`. Entire workflow
   tested from both source and **clean installed wheel** in disposable CI.

## Try the fixed, public toy engine — no markets, credentials or live actions

Run in a disposable development environment with Python 3.12.
The build is the isolated **new** distribution; **do not run the historical
`markets.sh` production-manager to install the new preview**.

```bash
# From a local clone of the public repository
python scripts/a6_prepare_package.py --destination /tmp/mmt-custom-stage
python -m pip install /tmp/mmt-custom-stage

naseri-custom sample --output-dir /tmp/mmt-custom-example
# Read the printed descriptor_sha256 and code_sha256 before registering.
naseri-custom --state-dir /tmp/mmt-custom-state register \
  --descriptor /tmp/mmt-custom-example/descriptor.json \
  --code /tmp/mmt-custom-example/public_toy_demo.py \
  --descriptor-sha256 <independently-reviewed-descriptor-sha256> \
  --code-sha256 <independently-reviewed-code-sha256> \
  --trust-local-code
naseri-custom --state-dir /tmp/mmt-custom-state list
naseri-custom --state-dir /tmp/mmt-custom-state enable public_toy_demo \
  --revision 1 --descriptor-sha256 <same-approved-descriptor-sha256>
naseri-custom --state-dir /tmp/mmt-custom-state paper public_toy_demo \
  --quote /tmp/mmt-custom-example/quote.json
naseri-custom --state-dir /tmp/mmt-custom-state signals --engine-id public_toy_demo
naseri-custom --state-dir /tmp/mmt-custom-state disable public_toy_demo \
  --revision 2
```

The sample export prints hashes **for convenience**, not as an independent
authentication channel. Compare with separately trusted values before
using any non-toy code. The bundled example intentionally emits a
**synthetic, deterministic toy PAPER signal** to prove system wiring.
It is NOT a profitable trading setup, backtest, trade recommendation or
real strategy. A Custom script can instead return `{"status":"no_signal"}`.

## Contract for a developer-created PUBLIC Custom engine

- Provide a **non-proprietary** A21 `public_custom/generic_custom`
  `descriptor.json` with accurately declared markets and version.
  No NYFR/private/commercial candidate metadata.
- Write one standalone Python 3.12 file that reads one JSON request from
  stdin (max 2 KiB), returning a single bounded, valid A7 PAPER envelope
  on stdout (max 8 KiB) or the exact `no_signal` object. Do not log
  secrets/diagnostics to stdout. No other output or interactive prompts.
- Each invocation is a new bounded **child process**; runs independently,
  not through `importlib`. Trade/order and Telegram permissions are absent.
  These are external pure-PAPER intents, not broker fills.
- The operator performs separate hash review of metadata and code,
  explicitly registers (local code snapshot), enables, runs and can disable
  the exact revision. Changes require a NEW review/registration lifecycle.
  Source is never pushed to GitHub by this registration.

## Important safety and product limitations

- **Trusted code only.** `python -I -S` blocks site-packages and shortens
  imports but is **not Linux isolation, seccomp, a container or a sandbox**.
  A malicious script could access the user's accessible files/network. No
  arbitrary remote plugin downloads or public install UI. Do not run
  untrusted Python on a privileged machine.
- **Offline only.** This standalone CLI implements the working Custom
  engine + PAPER journal journey. It does **not** deploy or wire the
  public Telegram transport to a running multi-market service, connect
  authenticated FX/MT5/crypto live market feeds, migrate the legacy
  PostgreSQL volume, or enable orders. Explicit market sessions/holidays
  are not certified by these one-tick synthetic fixtures.
- **Separate product path.** The historical A21–A27 fixed-fixture/trust
  proofs and separate A27 generation ledger remain unaffected. Local
  trusted code approval is not an A24 publisher signature, A25 signed
  executable release, commercial entitlement or production authorization.
- **Same-database PAPER atomicity scope.** This CLI serializes permission
  toggles and PAPER insertion within its OWN single SQLite file; it does
  not fence separate legacy settings stores or future real systems.
  A hostile host/user can still modify the local database or script.
- **OWNER ONLY:** NY First-Reversal can **never** be publicly installed,
  copied into a public sample, packaged, encrypted into a public wheel,
  served by this Custom distribution or relabeled as a public engine.
  The private core's deployment/commercialization requires a separate,
  explicit private design and authorization.

**Verdict after CI:** `TRUSTED_PUBLIC_CUSTOM_PAPER_MVP_VERIFIED_NONPRODUCTION`.

No A29, new license authority or production deployment was created.
