# MMT-FIX-05 — Installed public toy PAPER acceptance and restart guards

This is a nonproduction, bundled public-toy hardening step. The project
already has the naseri-paper-demo executable and an isolated wheel job.
No second engine, ledger, or deployment target is introduced.

## Red-to-green defects

Three negative tests first reproduced actual failures:
1. An injected init write exception left a half-created private state directory.
2. The demonstration accepted root/euid 0, despite running trusted local Python
   with caller privileges (Python -I -S is not a sandbox).
3. Inspect reopened SQLite even if another hard link pointed at the same inode,
   potentially sharing mutations outside the state scope.

Init now best-effort cleans up the newly-created private directory on failure.
Every action rejects root. Reopen requires the same owner UID, directory mode
0700, a private database and exactly one hard link. Existing operator consent,
revision/CAS gating, SHA pins, no-live paths and PAPER journal are retained.

## Clean-wheel evidence

The existing Stage-15 workflow tests in a Python 3.12 virtualenv outside the
repository, checks installed-wheel import provenance and dependency health,
then runs separate processes for each of:

1. Init without consent is refused and does not create state.
2. Explicit init produces disabled private 0700/0600 state.
3. Hard-linked ledger is refused, without another journal write.
4. Enable is explicitly revision- and descriptor-SHA-bound.
5. Synthetic replay is RECORDED, then a DUPLICATE replay is deduplicated.
6. Reopen in a fresh process retains the exact journal digest.
7. Disable via CAS preserves recorded history.
8. Relaxed state/database permissions are refused without compromising state.
9. Replay after disable is refused.
10. No Telegram, real broker, production, LIVE or credentials are involved.

## Explicit limitations

Success does not establish multi-market live trading, real broker reconciliation,
external provenance, strategy profitability or safe execution of third-party
Python. The trusted worker is not a generic sandbox. File pre-open validation
is not an atomic defense against malicious privileged filesystem races.
The cleanup on initialization failures is best-effort if the filesystem itself
cannot be written. No legacy Brooks source, NYFR private code, Production
database, services or LIVE exchange API is modified.
