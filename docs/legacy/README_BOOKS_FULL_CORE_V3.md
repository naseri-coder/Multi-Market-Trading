# Brooks Trilogy Full Core v3 — Additive Overlay

This overlay writes the **actual multi-family Brooks core** instead of continuing the
holdout-design loop.  It is based only on the three primary Al Brooks books already
provided by the user.

Added modules:

- `books_full_entities.py`
- `books_full_policy.py`
- `books_full_patterns.py`
- `books_full_engine.py`

The existing v1/v2 files are not deleted or replaced.  Production wiring is not changed
by the installer.

Use:

```python
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
engine = BrooksTrilogyFullCoreEngine()
result = await engine.evaluate(snapshot)
```

By default `result.decision` remains `NO_SIGNAL`, while a detected source-family setup is
reported in `result.setup_type` and `result.rule_evidence`.  This makes the full core
ready for deliberate wiring without silently turning on live/PAPER publication.
