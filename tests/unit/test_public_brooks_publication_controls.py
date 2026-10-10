"""Public Brooks panel publication intent remains distinct from actual delivery."""
import pytest

from naseri_markets.engine_control_store import (
    BROOKS_ENGINE_ID, OWNER_CORE_ID, EngineControlStore,
)
from naseri_markets.trusted_custom import LocalCustomRefused


def test_public_brooks_publication_request_is_persistent_but_never_sends(tmp_path):
    path = tmp_path / "private"
    with EngineControlStore(path) as store:
        before = store.publication(BROOKS_ENGINE_ID)
        assert before["revision"] == 0
        assert before["effective_publication"] is False
        changed = store.request_publication(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=0, actor_id=123)
        assert changed["requested_publication"] is True
        assert changed["effective_publication"] is False
        assert changed["reason"] == "NO_AUTHENTICATED_FORWARD_PUBLISHER"
        with pytest.raises(LocalCustomRefused, match="STALE"):
            store.request_publication(
                BROOKS_ENGINE_ID, enabled=False,
                expected_revision=0, actor_id=123)
        assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
        assert store.signals(BROOKS_ENGINE_ID) == []
    with EngineControlStore(path) as store:
        assert store.publication(BROOKS_ENGINE_ID)["requested_publication"]
        assert not store.publication(BROOKS_ENGINE_ID)["effective_publication"]
        disabled = store.request_publication(
            BROOKS_ENGINE_ID, enabled=False,
            expected_revision=1, actor_id=123)
        assert not disabled["requested_publication"]


def test_owner_custom_and_untrusted_actor_cannot_activate_publication(tmp_path):
    with EngineControlStore(tmp_path / "private", owner_visible=True) as store:
        store.register_owner_reference(engine_id=OWNER_CORE_ID, actor_id=123)
        with pytest.raises(LocalCustomRefused, match="PERMISSION_DENIED"):
            store.request_publication(
                OWNER_CORE_ID, enabled=True,
                expected_revision=0, actor_id=123)
        with pytest.raises(LocalCustomRefused, match="PERMISSION_DENIED"):
            store.request_publication(
                BROOKS_ENGINE_ID, enabled=True,
                expected_revision=0, actor_id=0)
