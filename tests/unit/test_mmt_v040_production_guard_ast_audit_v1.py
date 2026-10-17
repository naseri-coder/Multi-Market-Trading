"""Pure AST negative tests: no worker, production key, network or account."""
from __future__ import annotations
import pytest
from scripts import mmt_v040_production_guard_ast_audit_v1 as audit

@pytest.mark.parametrize("source", (
    b'if os.environ.get("MMT_PRODUCTION") == "1": raise ValueError()',
    b'if environment.get("MMT_PRODUCTION") == "1": raise ValueError()',
    b"if os.getenv('MMT_PRODUCTION') == '1': raise ValueError()",
    b'if "1" == os.environ.get("MMT_PRODUCTION"): raise ValueError()',
    b'if os.environ["MMT_PRODUCTION"] == "1": raise ValueError()',
    b'if os.environ.get("MMT_PRODUCTION") != "0": raise ValueError()',
    b'if (env.get("MMT_PRODUCTION") == "false"): raise ValueError()',
))
def test_value_only_guards_are_detected(source):
    assert audit.scan(source) == (1,)
    with pytest.raises(audit.ProductionGuardRefused, match="VALUE_ONLY_GUARDS_DENIED"):
        audit.require_no_value_only_guards({"naseri_markets/example.py": source})

@pytest.mark.parametrize("source", (
    b'if "MMT_PRODUCTION" in os.environ: raise ValueError()',
    b'if os.environ.get("MMT_NONPRODUCTION") != "1": raise ValueError()',
    b'# os.environ.get("MMT_PRODUCTION") == "1"\nx=2',
    b'x = "os.environ.get(\\\"MMT_PRODUCTION\\\") == \\\"1\\\""',
))
def test_safe_source_does_not_trigger_false_alarm(source):
    assert audit.scan(source) == ()
    answer=audit.require_no_value_only_guards({"naseri_markets/example.py":source})
    assert answer["value_only_guards"] == 0 and answer["live_trading_authorized"] is False


def test_syntax_error_refused_without_writes():
    with pytest.raises(audit.ProductionGuardRefused,match="SOURCE_AST_INVALID"):
        audit.scan(b"def broken(:")


def test_mixed_modules_fail_if_one_unsafe():
    modules={"naseri_markets/a.py":b'if "MMT_PRODUCTION" in os.environ: raise ValueError()',
             "naseri_markets/b.py":b'if env.get("MMT_PRODUCTION") == "1": raise ValueError()'}
    with pytest.raises(audit.ProductionGuardRefused,match="VALUE_ONLY_GUARDS_DENIED:1"):
        audit.require_no_value_only_guards(modules)
