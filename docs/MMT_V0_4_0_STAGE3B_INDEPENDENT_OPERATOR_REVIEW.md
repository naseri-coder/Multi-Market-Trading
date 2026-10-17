# Stage 3B — independent operator and publisher trust (v0.4.0)

**Disposition:** TECHNICAL_REVIEW_GATE_ONLY — no official publisher approval.

The existing stable Wheel verifier authenticates the publisher's detached
Ed25519 signature and exact Git-to-Wheel custody. Stage 3B adds a **distinct
operator review signature** with a separately authenticated public key, an
externally pinned signed-receipt SHA256 and an independently pinned reviewer
trust/revocation policy. The two roles must not reuse the same key.

The exact canonical operator-signed receipt binds the source Git commit,
226-file source tree and snapshot, approved stable metadata overlay, Wheel
SHA256, manifest SHA256, approved publisher SPKI SHA256 and publisher trust
policy SHA256. It carries an expiration and strictly offline/PAPER scope.
The full CLI checks operator proof *then* runs the existing package-custody
auditor; all successful outputs still deny automatic release and merging.

Implemented:
- scripts/mmt_v040_operator_two_role_admission_v1.py
- tests/unit/test_mmt_v040_operator_two_role_admission_v1.py
- .github/workflows/stage3b-two-role-release-review.yml

External acceptance is still missing: independently authenticated real
publisher and operator public-key fingerprints, independently approved signed
trust-policy digests, an actual offline-signed stable package manifest and a
separate valid operator review of the exact final SHA. Human protected-main
review and authorization also remain mandatory. Two public Binance/Bybit HTTPS
smoke tests require explicit opt-in or a separately reviewed scope exclusion.

**Never paste/upload private signing keys** to GitHub Actions or the chat.
Synthetic CI keys are not trusted release identities. No main merge, official
v0.4.0 tag, Production/Telmivo change, Telegram send or LIVE order is allowed.
The frozen legacy crypto-price-action v0.3.2 and private NY engine stay intact.
