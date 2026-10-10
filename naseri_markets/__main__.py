"""Offline NASERI MARKETS preview entrypoint. No implicit strategy activation."""
from .platform_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
