# RUNTIME-A5 — crash-persistent one-time review challenges

**Status: nonproduction, GitHub-only implementation. No runtime authorization.**

A4 validates signed claims but previously did not persist nonce issuance or
prevent another accepted review after process restart. A5 adds a private,
operator-controlled, SQLite challenge registry with FULL synchronous commits.
The database stores the SHA-256 of each randomly generated challenge, not
the plaintext nonce. Every record binds one language, OCI policy digest,
reviewed worker digest, host, trusted issuer, issue instant and expiry.

`RuntimeChallengeLedger.issue()` is restricted to an explicitly authorized
operator and `MMT_NONPRODUCTION=1`. Caller supplies a reviewed `RuntimeProfile`
and exact intended worker hash. The caller delivers the raw challenge nonce to
the security reviewer independently; it must not appear in Git history, worker
source, CI logs or bot messages.

`consume()` first runs A4's exact HMAC, host, language, image, policy, nonce
and validity checks and then checks the independently pinned worker digest.
Only one transaction can transition `ISSUED -> CONSUMED`; duplicate/restart
replays are rejected. Invalid MACs do not consume valid challenges.
The operator can `revoke()` only an unconsumed challenge. Review results
always say **no execution**, no worker install, no broker or Telegram and
no quarantine release.

## Explicit limitations

- Fake CI signing keys and fixture claims **cannot** certify a host. This
  stage neither probes Docker nor executes any strategy.
- The nonce registry is local SQLite, not shared cross-host custody. A
  privileged attacker who controls the database can rewrite or roll back its
  state. No external audit pin, independent signature or global ledger
  quorum is provided.
- Direct A1/A3 host calls still exist. A5 is not a mandatory system-wide
  dispatcher fence and **must not be treated as authorization to run code**.
- There is no new connector for Al Brooks/NYFR, no live integration,
  no deployment and no change to server, Telegram or Postgres.
- Host probe evidence from real disposable rootless/gVisor infrastructure,
  pinned publisher artifacts and signed independent audit custody remain
  prerequisites for later readiness work.

## Tests

`python -m pytest -q tests/unit/test_runtime_a5_nonce_custody.py`

Covers four runtime languages, restart persistence, cross-connection replay,
invalid MAC, independently pinned worker digest, nonce expiry, revocation,
admin/environment fencing, forged nonces, corrupt SQLite and zero subprocess
side effects. These are **source/unit** tests, not a live sandbox review.

**Verdict:** `A5_NONCE_CUSTODY_PREPARED_NO_RELEASE`.
