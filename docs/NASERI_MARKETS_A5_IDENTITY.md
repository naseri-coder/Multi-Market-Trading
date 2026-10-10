# A5 — Canonical GitHub identity and fail-closed engine installation plans

**Status:** git-only release-preserving migration. Not an installation of
forex, NYFR, broker, Telegram or an execution-capable product.

## The identities are deliberately different (for now)

| Layer | Canonical NOW | Compatibility held stable |
|---|---|---|
| Public Git repository | `naseri-coder/Multi-Market-Trading` | old GitHub links may redirect; updater requires the canonical origin |
| Product display | NASERI MARKETS | — |
| Primary manager launcher | `bash markets.sh` | `bash naseri.sh` continues to work |
| Python distribution and CLI | future new version required | `crypto-price-action==0.3.2`, `crypto-signal-bot` |
| Docker Compose project | future migration gated | `crypto-price-action` |
| Docker image/tag | future release gated | `crypto-price-action:v0.3.2` |
| PostgreSQL persistent volume | **NEVER RENAME BLINDLY** | `crypto-price-action_postgres_data` |

Changing only the Compose project name would make the old database volume appear
missing. Existing v0.3.2 release manifests and `Dockerfile.production`
remain byte-for-byte unchanged, including its historical OCI metadata.
That old image label is a **release provenance marker, not the new brand**.

## Actual implemented capabilities

- Canonical repository URLs in the public README, manager updater and current
  installation guide, with no silent acceptance of an old reposquattable
  Git origin. Clones with the old remote must be reviewed and manually updated:
  `git remote set-url origin https://github.com/naseri-coder/Multi-Market-Trading.git`
  (only after inspecting their actual origin).
- NASERI MARKETS menu branding and a tiny `markets.sh` launcher. The original
  `naseri.sh` remains a working alias.
- `scripts/identity_preflight.py --json`: read-only check of canonical Git
  identity, frozen distribution/Compose/volume, package entrypoint, source
  manifest shape and private-core import exclusion. Prints **no credentials**.
- `python scripts/engine_plan.py examples/engine-plan.example.json`:
  strictly bounded, metadata-only admission for public/legacy or **private**
  engines. All engines MUST be `enabled: false`; unsupported fields (including
  Git URLs, shell commands, tokens and source paths) are rejected. No source
  import, engine installation, Telegram send or broker I/O occurs.
- CI offline contract tests and fresh-checkout manager self-tests.

## Why source/package and release identity are NOT renamed in A5

The v0.3.2 distributed wheel installs the frozen `app` package from
`production_source`, rather than the new standalone `naseri_markets`
modules. Renaming its `pyproject.toml` distribution or Docker image now
would make the old release appear like an already-integrated multi-market
product. It is NOT: the new public modules have no live dispatch connection to
the old `app` service. Shipping that claim would be incorrect.

## Required next release migration gate

A separately authorized v0.4 release candidate must:
1. Freeze intended Brooks/FM adapters and external/private-engine ABI;
   document exactly which functionality is installed.
2. Build a new versioned Python package and Docker image while preserving the
   old release and database data. Validate a forward upgrade AND a restore
   from a real backup using two distinct isolated Compose projects.
3. Explicitly bind old/new volume names or migrate data with verified
   checksum/integrity evidence; never switch Compose names automatically.
4. Validate a clean clone using the new URL; full tests, SQL migrations,
   safe startup/shutdown, Telegram disabled; CodeQL and publication safety.
5. Require operator authorization for any real installation, server,
   broker connection, live Telegram or trading.

No private NYFR source is copied into this public repository.
