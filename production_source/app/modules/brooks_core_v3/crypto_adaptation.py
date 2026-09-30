"""Brooks Core v3 Phase 2 Crypto Adaptation Layer.

The layer enriches Brooks Foundation context with crypto-specific observations. It is
purely descriptive and cannot publish or execute a signal.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from statistics import median

from app.modules.brooks_core_v3.crypto_adaptation_entities import (
    CryptoAdaptationAssessment,
    CryptoAdaptationEvidence,
    CryptoAdaptationInput,
    DerivativesObservation,
    LiquidityObservation,
)
from app.modules.brooks_core_v3.crypto_adaptation_policy import CryptoAdaptationPolicy
from app.modules.brooks_core_v3.enums import (
    AlwaysIn,
    CryptoEvidenceSource,
    DerivativesBias,
    EvidenceStatus,
    FakeBreakoutState,
    LiquidityState,
    MTFAlignment,
    RelativeVolumeState,
    VolatilityState,
)
from app.modules.brooks_core_v3.foundation import BrooksCoreV3FoundationBuilder
from app.modules.market_data.entities import Candle

_ZERO = Decimal("0")
_ONE = Decimal("1")


def _evidence(
    evidence_id: str,
    *,
    status: EvidenceStatus,
    source: CryptoEvidenceSource,
    rationale: str,
    measurements: tuple[tuple[str, str], ...] = (),
) -> CryptoAdaptationEvidence:
    return CryptoAdaptationEvidence(
        evidence_id=evidence_id,
        status=status,
        source=source,
        rationale=rationale,
        measurements=measurements,
    )


def _true_range_fraction(current: Candle, previous: Candle) -> Decimal:
    denominator = previous.close if previous.close > 0 else current.close
    if denominator <= 0:
        return _ZERO
    true_range = max(
        current.high - current.low,
        abs(current.high - previous.close),
        abs(current.low - previous.close),
    )
    return true_range / denominator


def _volatility_state(
    candles: tuple[Candle, ...],
    policy: CryptoAdaptationPolicy,
) -> tuple[VolatilityState, Decimal | None, CryptoAdaptationEvidence, str | None]:
    required = policy.volatility_recent_bars + policy.volatility_baseline_bars + 1
    if len(candles) < required:
        return (
            VolatilityState.UNKNOWN,
            None,
            _evidence(
                "CA-VOL-001",
                status=EvidenceStatus.AMBIGUOUS,
                source=CryptoEvidenceSource.CLOSED_CANDLES,
                rationale="Not enough closed candles for volatility baseline comparison.",
                measurements=(
                    ("required_candles", str(required)),
                    ("actual_candles", str(len(candles))),
                ),
            ),
            "volatility_baseline_unavailable",
        )

    ranges = tuple(
        _true_range_fraction(current, previous)
        for previous, current in zip(candles, candles[1:])
    )
    recent = ranges[-policy.volatility_recent_bars :]
    baseline = ranges[
        -(policy.volatility_recent_bars + policy.volatility_baseline_bars)
        : -policy.volatility_recent_bars
    ]
    baseline_median = median(baseline)
    recent_median = median(recent)
    if baseline_median <= 0:
        return (
            VolatilityState.UNKNOWN,
            None,
            _evidence(
                "CA-VOL-001",
                status=EvidenceStatus.AMBIGUOUS,
                source=CryptoEvidenceSource.CLOSED_CANDLES,
                rationale="Volatility baseline is zero and cannot be normalized.",
            ),
            "volatility_baseline_zero",
        )

    ratio = recent_median / baseline_median
    if ratio >= policy.volatility_extreme_ratio:
        state = VolatilityState.EXTREME
    elif ratio >= policy.volatility_high_ratio:
        state = VolatilityState.HIGH
    elif ratio <= policy.volatility_low_ratio:
        state = VolatilityState.LOW
    else:
        state = VolatilityState.NORMAL

    item = _evidence(
        "CA-VOL-001",
        status=EvidenceStatus.PASS,
        source=CryptoEvidenceSource.CLOSED_CANDLES,
        rationale="Recent normalized true range was compared with a prior closed-bar baseline.",
        measurements=(("volatility_ratio", str(ratio)), ("state", state.value)),
    )
    return state, ratio, item, None


def _relative_volume_state(
    candles: tuple[Candle, ...],
    policy: CryptoAdaptationPolicy,
) -> tuple[RelativeVolumeState, Decimal | None, CryptoAdaptationEvidence, str | None]:
    required = policy.volume_baseline_bars + 1
    if len(candles) < required:
        return (
            RelativeVolumeState.UNKNOWN,
            None,
            _evidence(
                "CA-VOLUME-001",
                status=EvidenceStatus.AMBIGUOUS,
                source=CryptoEvidenceSource.CLOSED_CANDLES,
                rationale="Not enough closed candles for relative-volume baseline.",
                measurements=(
                    ("required_candles", str(required)),
                    ("actual_candles", str(len(candles))),
                ),
            ),
            "volume_baseline_unavailable",
        )

    baseline = tuple(c.volume for c in candles[-required:-1])
    baseline_median = median(baseline)
    if baseline_median <= 0:
        return (
            RelativeVolumeState.UNKNOWN,
            None,
            _evidence(
                "CA-VOLUME-001",
                status=EvidenceStatus.AMBIGUOUS,
                source=CryptoEvidenceSource.CLOSED_CANDLES,
                rationale="Volume baseline is zero and cannot be normalized.",
            ),
            "volume_baseline_zero",
        )
    ratio = candles[-1].volume / baseline_median
    if ratio >= policy.volume_spike_ratio:
        state = RelativeVolumeState.SPIKE
    elif ratio >= policy.volume_high_ratio:
        state = RelativeVolumeState.HIGH
    elif ratio <= policy.volume_low_ratio:
        state = RelativeVolumeState.LOW
    else:
        state = RelativeVolumeState.NORMAL

    item = _evidence(
        "CA-VOLUME-001",
        status=EvidenceStatus.PASS,
        source=CryptoEvidenceSource.CLOSED_CANDLES,
        rationale="Final closed-bar volume was normalized by the prior median volume.",
        measurements=(
            ("relative_volume_ratio", str(ratio)),
            ("state", state.value),
        ),
    )
    return state, ratio, item, None


def _fake_breakout_state(
    candles: tuple[Candle, ...],
    policy: CryptoAdaptationPolicy,
) -> tuple[FakeBreakoutState, Decimal | None, CryptoAdaptationEvidence, str | None]:
    required = policy.fake_breakout_range_bars + 1
    if len(candles) < required:
        return (
            FakeBreakoutState.UNKNOWN,
            None,
            _evidence(
                "CA-FAKEOUT-001",
                status=EvidenceStatus.AMBIGUOUS,
                source=CryptoEvidenceSource.CLOSED_CANDLES,
                rationale="Not enough closed candles for fake-breakout range context.",
                measurements=(
                    ("required_candles", str(required)),
                    ("actual_candles", str(len(candles))),
                ),
            ),
            "fake_breakout_context_unavailable",
        )

    last = len(candles) - 1
    first_probe = max(policy.fake_breakout_range_bars, last - policy.fake_breakout_rejection_bars)
    bull_traps: list[tuple[int, Decimal]] = []
    bear_traps: list[tuple[int, Decimal]] = []

    for index in range(first_probe, last + 1):
        prior = candles[index - policy.fake_breakout_range_bars : index]
        range_high = max(c.high for c in prior)
        range_low = min(c.low for c in prior)
        width = range_high - range_low
        if width <= 0:
            continue
        excursion = width * policy.fake_breakout_min_excursion_fraction
        probe = candles[index]
        final = candles[last]
        if probe.high >= range_high + excursion and final.close <= range_high:
            bull_traps.append((index, range_high))
        if probe.low <= range_low - excursion and final.close >= range_low:
            bear_traps.append((index, range_low))
    if bull_traps and bear_traps:
        state = FakeBreakoutState.AMBIGUOUS
        reference_level = None
    elif bull_traps:
        state = FakeBreakoutState.BULL_TRAP
        reference_level = bull_traps[-1][1]
    elif bear_traps:
        state = FakeBreakoutState.BEAR_TRAP
        reference_level = bear_traps[-1][1]
    else:
        state = FakeBreakoutState.NONE
        reference_level = None

    measurements = (
        ("state", state.value),
        ("bull_trap_count", str(len(bull_traps))),
        ("bear_trap_count", str(len(bear_traps))),
        ("reference_level", str(reference_level) if reference_level is not None else "NONE"),
    )
    item = _evidence(
        "CA-FAKEOUT-001",
        status=EvidenceStatus.PASS,
        source=CryptoEvidenceSource.CLOSED_CANDLES,
        rationale="Closed-bar probes were checked for rejection back inside their prior range.",
        measurements=measurements,
    )
    return state, reference_level, item, None


def _liquidity_state(
    observation: LiquidityObservation | None,
    policy: CryptoAdaptationPolicy,
) -> tuple[LiquidityState, CryptoAdaptationEvidence, str | None]:
    if observation is None:
        return (
            LiquidityState.UNKNOWN,
            _evidence(
                "CA-LIQ-001",
                status=EvidenceStatus.AMBIGUOUS,
                source=CryptoEvidenceSource.LIQUIDITY_OBSERVATION,
                rationale="No canonical liquidity observation was supplied.",
            ),
            "liquidity_observation_unavailable",
        )

    spread = observation.spread_bps
    imbalance = observation.bid_ask_depth_ratio
    depth_ratio = observation.depth_to_volume_ratio
    inverse_limit = _ONE / policy.liquidity_imbalance_ratio

    if imbalance is not None and (
        imbalance >= policy.liquidity_imbalance_ratio or imbalance <= inverse_limit
    ):
        state = LiquidityState.IMBALANCED
    elif (
        spread is not None and spread >= policy.liquidity_thin_spread_bps
    ) or (
        depth_ratio is not None and depth_ratio <= policy.liquidity_thin_depth_ratio
    ):
        state = LiquidityState.THIN
    elif (
        spread is not None
        and spread <= policy.liquidity_deep_spread_bps
        and depth_ratio is not None
        and depth_ratio >= policy.liquidity_deep_depth_ratio
    ):
        state = LiquidityState.DEEP
    else:
        state = LiquidityState.NORMAL

    values = (
        ("state", state.value),
        ("source", observation.source),
        ("spread_bps", str(spread) if spread is not None else "UNAVAILABLE"),
        ("bid_ask_depth_ratio", str(imbalance) if imbalance is not None else "UNAVAILABLE"),
        ("depth_to_volume_ratio", str(depth_ratio) if depth_ratio is not None else "UNAVAILABLE"),
    )
    return (
        state,
        _evidence(
            "CA-LIQ-001",
            status=EvidenceStatus.PASS,
            source=CryptoEvidenceSource.LIQUIDITY_OBSERVATION,
            rationale=(
                "Supplied public-market liquidity measurements were "
                "classified by versioned policy."
            ),
            measurements=values,
        ),
        None,
    )


def _derivatives_bias(
    observation: DerivativesObservation | None,
    policy: CryptoAdaptationPolicy,
) -> tuple[DerivativesBias, CryptoAdaptationEvidence, str | None]:
    if observation is None:
        return (
            DerivativesBias.UNKNOWN,
            _evidence(
                "CA-DERIV-001",
                status=EvidenceStatus.AMBIGUOUS,
                source=CryptoEvidenceSource.DERIVATIVES_OBSERVATION,
                rationale="No funding/open-interest observation was supplied.",
            ),
            "derivatives_observation_unavailable",
        )

    funding = observation.funding_rate
    oi_change = observation.open_interest_change_fraction
    if funding is None or oi_change is None:
        item = _evidence(
            "CA-DERIV-001",
            status=EvidenceStatus.AMBIGUOUS,
            source=CryptoEvidenceSource.DERIVATIVES_OBSERVATION,
            rationale=(
                "Funding and open-interest change are both required "
                "for crowding classification."
            ),
            measurements=(
                ("funding_rate", str(funding) if funding is not None else "UNAVAILABLE"),
                ("oi_change_fraction", str(oi_change) if oi_change is not None else "UNAVAILABLE"),
            ),
        )
        return DerivativesBias.UNKNOWN, item, "derivatives_observation_incomplete"
    if (
        funding >= policy.funding_crowded_abs_threshold
        and oi_change >= policy.open_interest_growth_threshold
    ):
        bias = DerivativesBias.LONG_CROWDED
    elif (
        funding <= -policy.funding_crowded_abs_threshold
        and oi_change >= policy.open_interest_growth_threshold
    ):
        bias = DerivativesBias.SHORT_CROWDED
    else:
        bias = DerivativesBias.BALANCED

    item = _evidence(
        "CA-DERIV-001",
        status=EvidenceStatus.PASS,
        source=CryptoEvidenceSource.DERIVATIVES_OBSERVATION,
        rationale="Funding and open-interest growth were classified as crypto crowding context.",
        measurements=(
            ("source", observation.source),
            ("funding_rate", str(funding)),
            (
                "open_interest",
                str(observation.open_interest)
                if observation.open_interest is not None
                else "UNAVAILABLE",
            ),
            ("oi_change_fraction", str(oi_change)),
            ("bias", bias.value),
        ),
    )
    return bias, item, None


def _input_fingerprint(data: CryptoAdaptationInput) -> str:
    liquidity = data.liquidity
    derivatives = data.derivatives
    payload = {
        "primary_snapshot_hash": data.primary_snapshot.snapshot_hash,
        "higher_timeframe_hashes": [
            snapshot.snapshot_hash for snapshot in data.higher_timeframe_snapshots
        ],
        "liquidity": None if liquidity is None else {
            "captured_at": liquidity.captured_at.isoformat(),
            "source": liquidity.source,
            "spread_bps": str(liquidity.spread_bps),
            "bid_ask_depth_ratio": str(liquidity.bid_ask_depth_ratio),
            "depth_to_volume_ratio": str(liquidity.depth_to_volume_ratio),
        },
        "derivatives": None if derivatives is None else {
            "captured_at": derivatives.captured_at.isoformat(),
            "source": derivatives.source,
            "funding_rate": str(derivatives.funding_rate),
            "open_interest": str(derivatives.open_interest),
            "open_interest_change_fraction": str(derivatives.open_interest_change_fraction),
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


class CryptoAdaptationEngine:
    engine_version = "brooks-core-v3-phase2-crypto-adaptation-v1"

    def __init__(
        self,
        *,
        policy: CryptoAdaptationPolicy | None = None,
        foundation_builder: BrooksCoreV3FoundationBuilder | None = None,
    ) -> None:
        self.policy = policy or CryptoAdaptationPolicy()
        self.foundation_builder = foundation_builder or BrooksCoreV3FoundationBuilder()

    def evaluate(self, data: CryptoAdaptationInput) -> CryptoAdaptationAssessment:
        foundation = self.foundation_builder.evaluate_foundation(data.primary_snapshot)
        candles = data.primary_snapshot.candles
        blockers = [
            "phase2_context_only_no_trade_decision",
            "phase2_no_signal_runtime_or_telegram_wiring",
        ]
        evidence: list[CryptoAdaptationEvidence] = []

        volatility_state, volatility_ratio, item, blocker = _volatility_state(
            candles,
            self.policy,
        )
        evidence.append(item)
        if blocker:
            blockers.append(blocker)
        volume_state, volume_ratio, item, blocker = _relative_volume_state(
            candles,
            self.policy,
        )
        evidence.append(item)
        if blocker:
            blockers.append(blocker)

        fakeout_state, fakeout_level, item, blocker = _fake_breakout_state(
            candles,
            self.policy,
        )
        evidence.append(item)
        if blocker:
            blockers.append(blocker)

        liquidity_state, item, blocker = _liquidity_state(data.liquidity, self.policy)
        evidence.append(item)
        if blocker:
            blockers.append(blocker)

        derivatives_bias, item, blocker = _derivatives_bias(data.derivatives, self.policy)
        evidence.append(item)
        if blocker:
            blockers.append(blocker)

        mtf_alignment, item, blocker = self._mtf_alignment(data, foundation.market_state.always_in)
        evidence.append(item)
        if blocker:
            blockers.append(blocker)
        return CryptoAdaptationAssessment(
            foundation=foundation,
            volatility_state=volatility_state,
            volatility_ratio=volatility_ratio,
            relative_volume_state=volume_state,
            relative_volume_ratio=volume_ratio,
            fake_breakout_state=fakeout_state,
            fake_breakout_reference_level=fakeout_level,
            liquidity_state=liquidity_state,
            derivatives_bias=derivatives_bias,
            mtf_alignment=mtf_alignment,
            evidence=tuple(evidence),
            blockers=tuple(dict.fromkeys(blockers)),
            configuration_version=self.policy.configuration_version,
            input_fingerprint=_input_fingerprint(data),
        )

    def _mtf_alignment(
        self,
        data: CryptoAdaptationInput,
        primary_direction: AlwaysIn,
    ) -> tuple[MTFAlignment, CryptoAdaptationEvidence, str | None]:
        if not data.higher_timeframe_snapshots:
            return (
                MTFAlignment.UNKNOWN,
                _evidence(
                    "CA-MTF-001",
                    status=EvidenceStatus.AMBIGUOUS,
                    source=CryptoEvidenceSource.MULTI_TIMEFRAME,
                    rationale="No higher-timeframe closed-bar snapshots were supplied.",
                ),
                "mtf_context_unavailable",
            )
        directions: list[tuple[str, AlwaysIn]] = [
            (data.primary_snapshot.timeframe, primary_direction)
        ]
        for snapshot in data.higher_timeframe_snapshots:
            foundation = self.foundation_builder.evaluate_foundation(snapshot)
            directions.append((snapshot.timeframe, foundation.market_state.always_in))

        resolved = [item for item in directions if item[1] != AlwaysIn.UNRESOLVED]
        measurement = "|".join(
            f"{timeframe}:{direction.value}"
            for timeframe, direction in directions
        )
        if len(resolved) < self.policy.mtf_min_resolved_timeframes:
            return (
                MTFAlignment.UNKNOWN,
                _evidence(
                    "CA-MTF-001",
                    status=EvidenceStatus.AMBIGUOUS,
                    source=CryptoEvidenceSource.MULTI_TIMEFRAME,
                    rationale="Too few resolved Always-In timeframes for MTF alignment.",
                    measurements=(("timeframes", measurement),),
                ),
                "mtf_resolved_context_insufficient",
            )

        resolved_directions = {direction for _, direction in resolved}
        if resolved_directions == {AlwaysIn.LONG}:
            alignment = MTFAlignment.ALIGNED_LONG
        elif resolved_directions == {AlwaysIn.SHORT}:
            alignment = MTFAlignment.ALIGNED_SHORT
        else:
            alignment = MTFAlignment.MIXED
        return (
            alignment,
            _evidence(
                "CA-MTF-001",
                status=EvidenceStatus.PASS,
                source=CryptoEvidenceSource.MULTI_TIMEFRAME,
                rationale="Resolved closed-bar Always-In states were compared across timeframes.",
                measurements=(
                    ("timeframes", measurement),
                    ("alignment", alignment.value),
                ),
            ),
            None,
        )
