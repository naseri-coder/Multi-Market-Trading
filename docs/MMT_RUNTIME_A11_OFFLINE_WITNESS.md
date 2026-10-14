# RUNTIME-A11 — Offline witness-media preparation (NO real independent custody)

**Verdict: RUNTIME_A11_OFFLINE_WITNESS_KIT_PREPARED_MEDIA_NOT_DESIGNATED**

A10 compares a caller-provided checkpoint to its local hash-chain but cannot
prove the checkpoint was held outside a compromised host. A11 introduces a
second *logical* role for physical offline transfer, not a new trusted
production service. No removable medium, independent computer, operator
signing authority, trusted time or off-host archive is designated or tested.

## Required physical separation, NOT implemented yet

- **A10 producer:** exports byte-exact canonical A10 anchor. This host must
  never hold the private witness HMAC key or witness database.
- **Witness operator:** physically receives and separately authenticates
  the A10 export, then maintains a private witness ledger on independently
  held media. The witness key must be randomly generated and remain private,
  never in the repository, inside Workers or in shell command arguments.
- **Reviewer:** securely and independently pins the latest witness receipt
  and witness ID as the trusted freshness floor, compares canonical receipt
  to canonical A10 anchor and separately runs A10 prefix comparison.

The CI key is fixed and public, so its HMAC does NOT establish genuine
identity, signatures or custody. CI exercises the algorithm only.

## Software implemented in this stage

The naseri_markets.runtime_a11_offline_witness library:
- Accepts exact A10 canonical ledger ID, sequence, hash and exported bytes.
- Creates a unique 128-bit witness ID and a monotonic local witness counter;
  consecutive witness receipts reference the exact preceding receipt SHA256.
- Uses domain-separated HMAC-SHA256, canonical bounded JSON, exact schema,
  owner-only private SQLite and synchronous FULL transactions.
- Revalidates every saved signed row; denies tampering, repeated or regressing
  A10 version, missing or stale prior signed receipt, forged HMAC, wrong
  witness identity, unrelated A10 anchor and missing witness links.
- Requires explicit nonproduction mode, authorized operator acknowledgement
  and a caller-provided out-of-band key of at least 32 bytes.
- On review, a caller-supplied trusted floor rejects any older receipt;
  when immediately consecutive, requires the exact previous-receipt SHA.
  Missing intermediate receipts fail closed. With no supplied floor,
  signature verification NEVER claims freshness.
- Exposes only inert reviews: Worker execution, quarantine release, broker,
  Telegram, physical host security and independent custody flags all FALSE.

## Important limitations

HMAC proves possession of a shared key; it is NOT independent public-key
identity. The software cannot prove the witness computer or USB device is
distinct from the producer host, the witness key is separately protected,
the A10 anchor is authentic, or the media is write-once.

A privileged attacker can restore an old internally consistent witness
database. This attack is detectable **only** when a newer, independently
retained witness receipt survives outside the same rollback domain and is
supplied as the floor. If both database and floor are rolled back together,
this software cannot detect the event. Local operator clocks are untrusted.

Tests simulate two ephemeral databases, copied/rewound witness state, tamper,
forgery, stale receipt, wrong HMAC/witness identity, missing links, restart,
operator/environment denials and unchanged A6 hard stop. No real media
or separate host is used.

## Later, independent physical acceptance gate

1. Designate an air-gapped operator-owned device and separate write-once
   or independently controlled custody medium.
2. Enroll witness ID, independently manage and back up the signing secret,
   and rotate custody without revealing keys to the producer/Workers.
3. Transfer exact A10 bytes offline and preserve the newest receipt as an
   externally trusted monotonic floor. Reconcile every missing link.
4. Test host and witness DB rollback, USB corruption, lost devices, stolen
   HMAC keys, replay, forking, broken clock and recovery. Archive evidence.
5. Only a separate approved stage can authorize changes to A6.

No production host, bot, broker, Telegram, PostgreSQL or Worker is touched.

**A6 remains DENY. Independent media custody = NOT_PROVEN.**
