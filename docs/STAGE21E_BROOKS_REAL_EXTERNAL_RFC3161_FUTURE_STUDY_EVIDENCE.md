# Stage 21E — Real Public RFC3161-Stamped Brooks Research Precommitment

**Evidence obtained: genuine, digitally signed external FreeTSA RFC3161 timestamp. Status is RESEARCH-ONLY, not independently accredited TSA custody approval, not OOS, not PAPER activation.**

## Executed single request and independently repeated validation

- Code review branch: Draft PR #310, stacked on Draft Stage21D #308; no merge.
- FreeTSA's publicly documented RFC3161 service: https://freetsa.org/tsr
- FreeTSA's official published root and signer files: https://freetsa.org/files/cacert.pem and https://freetsa.org/files/tsa.crt
- Public certificate discovery CI run: `38835711245`.
- **Actual external notarization** CI run: `38835965013` on nonproduction Ubuntu runner with only `contents:read` permissions.
- Confirmed independent second execution of `openssl ts -verify -data original-plan.json -in external-response.tsr -CAfile root.pem -untrusted signer.pem` returned **Verification: OK**. Original binary response (4633 bytes), request (59 bytes), original unsigned plan (709 bytes), public certificate bytes and source audit receipts preserved as a non-executable ZIP artifact.
- Original exact frozen plan is also copied byte-for-byte into the repository at `docs/evidence/STAGE21E_BROOKS_ORIGINAL_EXTERNALLY_TIMESTAMPED_PLAN_20261016.json`. It contains NO trading credentials, keys, personal user data or client secrets.

## Exact original published-content cryptographic digests

| Input | SHA-256 |
| --- | --- |
| Exact original 709-byte plan | `c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d` |
| Genuine FreeTSA timestamp response DER | `2e36862213d0f32cffadf161b3edae2610b03eef32f49e3b368253b49f83cf75` |
| Exact timestamp query ASN.1 DER | `e2319952ed7a3c7d827cf3c3c77bdfc6ef6757cb7d2dc8f546d3dee3c52970e7` |
| FreeTSA X.509 root PEM | `2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438` |
| FreeTSA timestamp signer PEM | `8bfb0305bb64e2571ca507552ef3245cb1c2fee8728e0ff8689225081ea13467` |
| Frozen Stage21B source bytes | `9683277e5e3c4db83e4bfc5afd460bb7eb22d8e2a7062a2ade1bbc07159d93aa` |
| Operator-UNVERIFIED fixed economics assumptions | `0512df973f0c3098d512d4606f4530f1d2c514618400eea2082ad5a37c5b32f5` |
| Artifact outer ZIP | `7e05a160c1f4dc0740ca18604456924df81e8254a3455dab76643f9106809868` |

### Timestamp-bound research protocol

- Signed UTC time from **the RFC3161 token**, not a local clock: **2026-10-16 01:36:00Z**.
- Study start frozen at **2026-10-20 00:00:00Z**.
- Study end frozen at **2026-11-03 00:00:00Z**.
- Market: BTCUSDT Binance USD-M 15-minute candles.
- Frozen actual Brooks V5 legacy 359-file manifest SHA256: `1a15f9d4b40b07c05186d27f694f9ce71cd007dd5047a35b25b6811f9bc67335`.
- Expected 60 closed-bar warmup before model evaluation, source receipt batches capped at 96 future closed candles.
- Missing funding: always **REFUSE**, never zero-fill. Simultaneous stop and TP: **STOP FIRST**.
- `paper_market_access=false` and NO external exchange credentials.
- All fee/tick/slippage/contract assumptions are **operator-unverified placeholders**, not historic Binance account fees; changing economic assumptions or frozen code after timestamp invalidates the original plan for the modified protocol.

## Preserve and reproduce

GitHub Actions artifact `12019181218`, name `stage21e-external-rfc3161-brooks-preregistration`, configured with 30-day retention. The artifact contains:

```text
exact-frozen-brooks-plan.json
original-external-timestamp-response.tsr
plan-rfc3161-request.tsq
tsa-root-public.pem
tsa-signer-public.pem
locked-unverified-economic-assumptions.json
external-rfc3161-verification-receipt.json
operator-admission-audit.json
```

After extracting the original ZIP in a nonproduction research folder, verify original SHA hashes above then run:

```bash
openssl ts -verify \
  -data exact-frozen-brooks-plan.json \
  -in original-external-timestamp-response.tsr \
  -CAfile tsa-root-public.pem \
  -untrusted tsa-signer-public.pem
```

Expected: `Verification: OK`. The timestamp response is digitally signed by the private key corresponding to the **operator-pinned FreeTSA certificate**. This cryptographic verification does not by itself prove that FreeTSA's identity, legal accreditation, long-term certificate revocation or conflict of interest has been independently assessed.

## Acceptance gates remain **closed**

**This is pre-registration evidence, not data collection or an actual forward study.** No provider-original future market candles, historical correction logs, exchange-authenticated timestamp for price observations, account-specific fees, precise Mark settlement, depth/fill evidence, actual position executions, profit factor or OOS performance has been obtained. The interval is scheduled in the future. No hourly automation, service, order or PAPER bot has been started. A frozen plan signed today cannot itself collect or evaluate October 20–November 3 market data.

The separately protected CodeQL and Publication Safety must be run on the exact final commit; they are not to be weakened. All stacked Draft PRs require independent dependency review before any `main` merge. Do not merge the duplicate historical security-audit PR #309.

**Evidence classification: `STAGE21E_REAL_EXTERNAL_RFC3161_SIGNATURE_AND_HASH_PASS_INDEPENDENT_CUSTODY_POLICY_PENDING`.**
