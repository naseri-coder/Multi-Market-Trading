"""Exact distribution versions accepted by inert/offline public platform surfaces.

This is a version-identity check, NOT a signed-release, installation,
production, public-signal or live-trading authorization decision.
"""
from __future__ import annotations

_ALLOWED_OFFLINE_VERSIONS = frozenset(("0.4.0rc1", "0.4.0"))


def require_offline_platform_version(release: str) -> str:
    """Accept only the frozen RC or its eventual stable offline successor."""
    if type(release) is not str or release not in _ALLOWED_OFFLINE_VERSIONS:
        raise ValueError("UNEXPECTED_RELEASE_VERSION")
    return release
