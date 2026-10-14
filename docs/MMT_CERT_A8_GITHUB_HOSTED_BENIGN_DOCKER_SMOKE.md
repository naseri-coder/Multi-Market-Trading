# CERT-A8 — hosted GitHub Actions rootful Docker boundary smoke

**Status: NONPRODUCTION CI VALIDATION ONLY. NOT ROOTLESS/gVisor CERTIFICATION.**

## Rationale

TELMIVO is an active application server with existing containers; it must
NOT be repurposed as a hostile-strategy sandbox. A real independently
designated disposable rootless Docker + gVisor host is still unavailable.

Existing RUNTIME-A2 GitHub Actions already builds an ephemeral *candidate*
Docker image and executes four harmless committed language fixtures.
CERT-A8 reuses that SAME build and GitHub-hosted worker — no new server,
deployment, runner, image publication or additional container image build.

## What the added live CI step checks

The fixed source is committed as scripts/ci_cert_a8_rootful_docker_smoke.py.
It will run only with explicit GitHub-hosted, nonproduction environment
flags and a hard-coded local candidate image, with *no caller-supplied
image or code*. GitHub environment indicators are defense in depth rather
than tamper-resistant host identity.

The host invokes normal Docker (NOT gVisor) with:
- network=none, ipc=none, read-only rootfs, non-root uid/gid 65534;
- dropped Linux capabilities, no-new-privileges, no mounts or inherited
  credentials, no on-demand image pull, capped CPU/memory/PIDs/nofile;
- an 8 MiB writable noexec tmpfs at /tmp and short process deadline.

A fixed Python probe within the guest checks the following, returning only
seven strict booleans:
1. effective UID 65534;
2. refused write in read-only filesystem root;
3. small test write in /tmp succeeds;
4. the guest sees only the loopback network interface, not eth0/veth;
5. zero effective Linux capabilities and NoNewPrivs=1 in /proc;
6. cgroup v2 limits for memory <=128 MiB, pids <=32, CPU quota <=0.5 core
   plus exactly 64 open-file soft and hard limits;
7. selected common credential environment variable **names** are absent.

The guest performs no external network connections. This is an internal
namespace/flag observation, not evidence that external connectivity is
impossible across all paths.

The host refuses unexpected/missing/nonboolean/duplicated guest fields,
a nonzero exit, timeout or output over its bound. It always requests cleanup,
confirms Docker daemon responsiveness, and checks the generated container
name is absent. These are not independent process-orphan attestations.

## CI changes and limits

Only existing .github/workflows/runtime-a2-worker-smoke.yml is extended.
Its existing actual four-language fixed-fixture job remains intact. It adds
mock-only unit tests of the new runner probe. Its already-existing ephemeral
candidate-container job runs the bounded real Docker probe **after** building
the candidate and verifying the four harmless language roundtrips.

The image build uses the pre-existing mutable Python base and unverified
dependency packages; passing CERT-A8 does NOT certify that image's publisher,
toolchain, content provenance, reproducibility or security. The hosted runner
is privileged/rootful relative to its Docker daemon, not a rootless+runsc
isolation target. These are basic runtime configuration observations ONLY.

No uploaded code, live strategy, trading engine, keys, broker, Telegram,
production host, database, deployment, quarantine release, Worker registry,
or A1/A3 launch authorization is involved. RUNTIME-A6 is unchanged and must
continue to unconditionally deny every Worker launch.

## Verdicts

- CI not checked yet: CERT_A8_SOURCE_PREPARED_CI_UNVERIFIED.
- Dedicated tests and actual fixed Docker smoke pass:
  CERT_A8_GITHUB_ROOTFUL_BENIGN_CONTAINER_SMOKE_ONLY.
- CERT-A6 external containment certification:
  BLOCKED_INDEPENDENT_GVISOR_HOST_AND_SUPPLY_CHAIN.

Do not record independent host isolation, arbitrary language strategy
execution approval, PnL/market-data provenance, or production release as PASS.
