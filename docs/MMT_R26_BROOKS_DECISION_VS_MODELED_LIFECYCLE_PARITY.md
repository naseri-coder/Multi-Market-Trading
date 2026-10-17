# MMT-R26 — Frozen Brooks V5 decision-to-modeled-trade economic parity

**Scope: isolated, source-frozen offline research. NOT a market backtest, real filled trade, confirmed OOS test, connected PAPER or LIVE order.**

## Why this phase is different

R24/R25 prevent unreviewed market-data revision or a missed first-window candle from silently contaminating the frozen prospective study. R26 is a **separate audit of decision attribution and scenario-only cashflow arithmetic**. The legitimate Stage15 frozen Brooks V5 worker produces **one decision** with a pinned 359-file source manifest. Only AFTER that worker completes do two independently supplied *hypothetical future paths* enter the model. They can alter stop/target outcomes and modeled costs but **must not alter the previously obtained decision, cutoff, entry intent or snapshot evidence**.

Original Brooks source manifest SHA256: `1a15f9d4b40b07c05186d27f694f9ce71cd007dd5047a35b25b6811f9bc67335`. The external FreeTSA-signed pre-study plan remains SHA256 `c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d`. R26 makes **zero changes** to the original worker, to the timestamped study plan, to Stage21B's frozen economics bridge (whose source digest is bound by the signed plan), and to original historical Kline/Funding/Mark evidence.

**This is NOT proof that the actual Brooks strategy would issue a matching exchange order.** Stage21's next-open market assumption ignores real market-depth fills, latency, unfilled orders, trading rules, slippage distribution, maintenance margin, account-specific tier and exchange statements. All related trust/accuracy flags remain explicitly false.

## Source decision and scenario boundary

`naseri_markets/brooks_frozen_decision_parity_mmt_r26_v1.py` implements `r26_audit_frozen_brooks_two_paths`:

1. Fail closed unless explicit `MMT_NONPRODUCTION=1`, no production mode, valid original predecision replay, **exactly two distinct, labeled, bounded postdecision future datasets**, original contract-metadata bytes and separately pinned SHA256.
2. Evaluate original Stage15/21 frozen Brooks worker **exactly once** through the unmodified `_source` (validates frozen source manifest, real decision rules, source-bound snapshot and entry/stop/target geometry). The worker receives only **predecision closed candles**.
3. Replay two different **strictly contiguous** sets of later closed candles through the existing `_validated_continuation`, then reuse the existing unmodified `_model_next_open` lifecycle. Scenarios may end at different stops/targets; they can never modify the sealed decision or turn it into a filled broker order.
4. Independently recompute exact `Decimal` mathematical gross PnL, two-sided taker fees, two-sided adverse-slip proxy, directional USD-M funding cashflow from operator-provided funding/mark events **only through the modeled exit time**, and net quote. Require equality with the original Stage16 model. **If anything disagrees, reject; do not output a PASS.** Neither arithmetic implementation is a venue witness.
5. Attribute separate exact input and output SHA256 hashes, only claims actual-model arithmetic parity where the model created a *hypothetical* position; `NO_SIGNAL` and rejected next-open entries **must have no recorded net profit or loss**.

Model formula, with `sign = +1` for LONG and `-1` for SHORT, quantity `q`, contract multiplier `m`, entry `E`, exit `X`, operator-assumed taker fee `f`, adverse slippage `s`, funding rate `r_t` and operator-supplied settlement mark `M_t`:

```
Gross           = sign × q × m × (X - E)
Taker fee proxy = q × m × (E + X) × f
Slip proxy      = q × m × (E + X) × s
Funding proxy   = Σ[-sign × q × m × M_t × r_t] for E_time < t ≤ X_time
Model net       = Gross - Taker fee proxy - Slip proxy + Funding proxy
```

The net above is a **scenario arithmetic result**, not actual realized PnL, a market-calibrated slippage model, a validated liquidation engine or evidence of edge. The existing Stage21 model uses **stop-first priority** whenever both stop and target are touched within the same candle, refuses an excessive next-open gap and caps favorable TP exits.

## Offline Termux CLI — no HTTP requests

Entry point: `scripts/mmt_r26_offline_brooks_decision_cashflow_audit_v1.py`. Four operator-prepared inputs are required:

- `--original-predecision-replay`: an existing canonical predecision Brooks replay context JSON. **Never put future bars in this file**.
- `--two-futures-json`: exactly two differently labeled, distinct `future_candles` arrays (strictly consecutive after signal cutoff) and each one's predeclared funding event list.
- `--economic-metadata`: explicit *operator-assumed* BTCUSDT USD-M contract/fee/slip metadata JSON, not represented as an exchange-certified fee tier.
- `--economic-metadata-sha256`: exact digest of that metadata, `--quantity-contracts`: separate quantity scenario. The `--frozen-source-dir` defaults to the source-verified `production_source` tree, read-only.

Example invocation **only after you have locally constructed the exact inputs**:

```bash
cd "$HOME/mmt-r26-source"
MMT_NONPRODUCTION=1 MMT_PRODUCTION=0 \
python scripts/mmt_r26_offline_brooks_decision_cashflow_audit_v1.py \
  --ack-research-only \
  --original-predecision-replay "$HOME/mmt-research/decision-prefix.json" \
  --two-futures-json "$HOME/mmt-research/two-counterfactual-paths.json" \
  --economic-metadata "$HOME/mmt-research/operator-contract-scenario.json" \
  --economic-metadata-sha256 <EXACT_SHA256_OF_METADATA> \
  --quantity-contracts 1
```

Required two-path input format (these prices are deliberately **SYNTHETIC DEMONSTRATION ONLY**, and not a source of market evidence):

```json
{
  "protocol": "MMT_R26_TWO_OPERATOR_HYPOTHETICAL_PATHS_V1",
  "scenarios": [
    {
      "label": "flat_future",
      "future_candles": [],
      "expected_funding_instants": [],
      "funding_events": []
    },
    {
      "label": "adverse_future",
      "future_candles": [],
      "expected_funding_instants": [],
      "funding_events": []
    }
  ]
}
```

The empty candle arrays above deliberately **cannot run**; operators must supply genuine, valid 15m *hypothetical* bars starting exactly after the decision cutoff. Funding instant strings and funding event `at` must be UTC-aware ISO timestamps. This is not a preapproved new strategy input policy.

## Anti-leakage and evidence trust boundaries

- Actual frozen Brooks V5 engine is evaluated once **before either postdecision path** is admitted. Each modeled path references the **same** decision cutoff, engine source manifest, decision evidence SHA and snapshot hash.
- Both paths are what-if tests, **not** true unseen future market prices, exchange-source verified responses or future live execution traces.
- Stop-target same-bar ambiguity resolves conservatively to stop, **not** a claim about actual exchange fill sequence. Adverse stop gap uses worse opening price, but actual order fill may be even worse.
- Independent cashflow arithmetic detects incorrect or inconsistent values in Stage16/21; it cannot validate that a user's historical broker charged those fees or that the actual strategy fills at those prices.
- Historical source issuer identity, true fee tier, liquidity/latency, funding/Mark settlement and exchange order IDs are unverified. **No statistical return distribution or strategy profitability is inferred from two counterfactuals.**
- Original Oct 16 timestamped plan is unchanged; R26 itself is a post-timestamp code audit and must not be silently passed off as a precommitted prospective trading evaluation.
- Production, GitHub main, Telegram, broker, connected PAPER and live orders are untouched. All research PRs remain Draft. Main-target audit PR #309 is **DO NOT MERGE**.

## Acceptance criteria

- Verify actual source-pinned frozen V5 subprocess runs once on a predecision context, and **both** distinct synthetic postdecision paths produce separately labeled results referring to the original immutable decision.
- Test LONG and SHORT, fee, slippage and funding sign/time, same-bar stop-first, NO_SIGNAL, gap-refused entry, invalid funding and explicit malformed metadata or disabled operator approval; **detect a deliberately corrupted PnL value**.
- Public tracked test corpus and Ruff, real GitHub Advanced Security CodeQL, native PostgreSQL and both unchanged protected Publication Safety checks must succeed on final exact commit. No bypass or main merge.
- Research outputs must not authorize OOS, connected PAPER or actual trading.

**Target verdict: MMT_R26_FROZEN_DECISION_AND_INDEPENDENT_MODEL_MATH_CODE_PASS — ACTUAL_BROKER_FILL_PARITY_AND_TRUE_OOS_UNPROVEN.**
