from app.modules.brooks_core.books_policy import BrooksBooksPolicy


def test_books_policy_is_shadow_disabled_by_default():
    policy = BrooksBooksPolicy()
    assert policy.enable_trade_decisions is False
    assert "books-v2-eng" in policy.configuration_version
    assert "exec0" in policy.configuration_version
