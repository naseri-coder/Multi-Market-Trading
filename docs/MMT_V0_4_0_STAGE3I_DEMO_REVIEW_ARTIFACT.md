# Stage 3I — reproducible OFFLINE demo review bundle (NOT a release)

**Status:** review experiment, no authorized stable version. This stage extends the successful Stage3H disposable demo-only Wheel acceptance. It does not alter the protected main, the 80/80-green release/0.4.0-candidate PR #352, or the existing nine-CLI candidate Wheel.

**Lineage:** source candidate SHA 7bbb3541fb6d63f960bee9f197fe026ed6d04608; prior Stage3H experimental HEAD 4f32d71486a67f60897f6eb6418de3e65ab18fc8; new branch ci/stage3i-demo-artifact-review-20261017. Only the three Stage3H and three Stage3I experiment CI/scripts/docs may differ from the candidate. Product source Git subtree must exactly match 511e9346d88280f3be7c80367f8822a8eaa24dd7.

## Acceptance objectives

1. Two independent disposable builds of multi-market-trading-offline-demo==0.4.0rc1 contain only nineteen exact original source modules and two console scripts naseri-paper-demo and naseri-brooks-replay. The new wheel is a separately named unapproved experiment, not the official multi-market-trading distribution.
2. Inspect the complete real Wheel ZIP. For every member: verify nonduplicate names, no traversal, no executable startup .pth injection, no symlink, no oversized file, and exact expected dist-info/RECORD paths.
3. Validate every SHA256/length from the wheel RECORD, exact source Python bytes against the immutable Git source tree, unmodified distribution/version/Python metadata and exact two entrypoints.
4. Actively reject four mutations: changed Python source with stale RECORD, extraneous startup .pth, altered console script with stale RECORD, and altered Python source with attacker-recomputed valid RECORD (still must fail original Git byte custody).
5. Install in a disposable Python 3.12 venv. Ensure seven unwanted CLI entrypoints and known network-feed/admin/service modules are absent. Run an installed toy PAPER init/enable/replay/inspect cycle with a real Linux network namespace without networking. Cannot silently fall back to a networked environment.
6. Only after all proof gates succeed, create one short-retention (one day) GitHub Actions review artifact containing an unsigned Wheel, REVIEW_ONLY.json with per-file source SHA256 and a NOT_A_RELEASE.txt warning. No PyPI upload, signed GitHub Release, OCI image, or public production installer.
7. Mark release_authorized=false, human_scope_approved=false, publisher_key_authenticated=false; the standalone experimental SHA256 is not an authenticated publisher signature.

## Known blockers unchanged

Both originally authorized public integration tests failed upstream (Binance USD-M HTTP 451; Bybit Spot HTTP 403), not passed. No evasion or geographic proxying is permitted. The original candidate retains network-capable CLI entrypoints, even though its GitHub CI is green. This review bundle cannot approve protected-main merger, v0.4.0 tag, user installation/Production, Telmivo, Telegram message publishing, external plugins, owner-private NY First-Reversal, or LIVE orders.

**Next real decision:** independent human acceptance of which distribution to release (separate tiny demo vs full development platform); then explicit branch-pinned public packaging policy, reviewed source and signed artifact manifest, verified distinct real-world publisher/operator keys/policies and protected GitHub branch reviews. Do not reinterpret this experiment as that decision.
