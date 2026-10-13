# RUNTIME-A7 — designated disposable-host preflight

Status: A7_PREFLIGHT_PREPARED_HOST_REQUIRED — NOT CERTIFIED.

A6's mandatory Worker launch hard stop remains unchanged. A7 is a
read-only observation tool. It never executes, creates, pulls, starts,
builds or installs a container or a strategy. Neither success of this
tool nor a valid A4/A5 receipt authorizes any Worker launch.

Operator prerequisites: a newly designated disposable NONPRODUCTION
Linux host separate from Telmivo, License Authority, trading servers
and databases; non-root account, private rootless Docker socket,
runsc registered in Docker with its absolute binary path; externally
reviewed SHA256 of runsc and locally cached digest-addressed worker
image. No user secrets or strategy files.

Only on that approved temporary host, execute:

    MMT_NONPRODUCTION=1 python -m \
      naseri_markets.runtime_a7_disposable_host_preflight \
      --host-id disposable.a7.unique \
      --image registry.example/worker@sha256:YOUR_REAL_64_HEX_DIGEST \
      --runsc /usr/local/bin/runsc \
      --runsc-sha256 YOUR_INDEPENDENT_REAL_64_HEX_DIGEST \
      --ack-disposable-host

This performs bounded read-only Docker info, local image inspect and
runsc --version queries after owner/mode checks. It does NOT prove actual
OCI runtime selection, kernel containment, no-network, readonly FS,
quota enforcement, provenance or cleanup. Real isolated harmless-fixture
execution and adversarial tests require separate host designation,
evidence custody and explicit later authorization.

CI only mocks these queries and tests fail-closed conditions; it must
not run a container or use any attached production host. GitHub runner
claims are not independent attestation.

Final A7 outcome remains BLOCKED_HOST_NOT_DESIGNATED.
