"""Historical reference only; not current release proof or runtime source.
Original source: integration_phase1/tests/test_integration_contract.py
Original SHA256: 4cf97d95a43e53b32c9dc9815559eb0850bba142c36678986b5fbc9a7bd0ed30
"""
from decimal import Decimal
from contracts.brooks_signal_contract import BrooksRuleEvidence, BrooksSignalImport

evidence=(BrooksRuleEvidence("BR-007","PASS",(11,),evidence=(("setup","H2"),)),)
cmd=BrooksSignalImport(
    source_signal_id="core-sig-1",
    symbol="BTCUSDT",
    direction="LONG",
    entry_price=Decimal("100"),
    stop_loss=Decimal("95"),
    targets=(Decimal("110"),Decimal("120")),
    leverage=Decimal("1"),
    exchange="binance",
    market_type="spot",
    timeframe="15m",
    setup_type="H2",
    market_snapshot_id="snap-1",
    market_snapshot_hash="abc123",
    engine_version="0.10.0",
    rule_set_version="phase2-catalog-v1",
    configuration_version="cfg-sha256-001",
    reasoning=("context aligned","risk valid"),
    rule_ids=("BR-007",),
    failed_rules=(),
    rule_evidence=evidence,
    generation_mode="PAPER",
    publication_scope="PRIVATE_TEST",
    counts_toward_performance=False,
)
mapped=cmd.to_existing_create_signal()
assert mapped.symbol=="BTCUSDT"
assert mapped.direction=="LONG"
assert mapped.entry_price==Decimal("100")
assert mapped.stop_loss==Decimal("95")
assert mapped.leverage==Decimal("1")
assert mapped.as_draft is False
print("EXISTING_CREATE_SIGNAL_MAPPING=PASS")

assert len(cmd.idempotency_key)==64
same=BrooksSignalImport(**{**{f:getattr(cmd,f) for f in cmd.__dataclass_fields__}})
assert same.idempotency_key==cmd.idempotency_key
print("IDEMPOTENCY_DETERMINISM=PASS")

try:
    BrooksSignalImport(**{
        **{f:getattr(cmd,f) for f in cmd.__dataclass_fields__},
        "publication_scope":"PUBLIC",
    })
    raise AssertionError("PAPER public scope must fail")
except ValueError:
    pass
print("PAPER_PUBLIC_LEAK_GUARD=PASS")

try:
    BrooksSignalImport(**{
        **{f:getattr(cmd,f) for f in cmd.__dataclass_fields__},
        "counts_toward_performance":True,
    })
    raise AssertionError("PAPER performance count must fail")
except ValueError:
    pass
print("PAPER_WINRATE_CONTAMINATION_GUARD=PASS")

try:
    BrooksSignalImport(**{
        **{f:getattr(cmd,f) for f in cmd.__dataclass_fields__},
        "configuration_version":"",
    })
    raise AssertionError("unversioned config must fail")
except ValueError:
    pass
print("CONFIGURATION_VERSION_REQUIRED=PASS")
