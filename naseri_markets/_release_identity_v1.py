"""Single, package-local identity for the independently installed MMT platform.

Exactly one source constant is promoted alongside platform_release/pyproject.toml
after all stable-release acceptance. This module is inert on import.
The frozen crypto-price-action 0.3.2 legacy package is separate.
"""
from __future__ import annotations

PLATFORM_DISTRIBUTION = "multi-market-trading"
PLATFORM_VERSION = "0.4.0rc1"


def exact_platform_version(value: object) -> bool:
    """Disallow another distribution, release, local suffix or normalized alias."""
    return type(value) is str and value == PLATFORM_VERSION
