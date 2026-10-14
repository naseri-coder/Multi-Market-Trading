"""CERT-A18 exact-path guard for an A15-derived no-publish candidate.

This verifies fixed build-only Debian JavaScript import roots were NOT
copied into the final image. It is not an upstream CVE patch, package
signature validation or proof that equivalent code is absent elsewhere.
"""
from __future__ import annotations

from pathlib import Path

_BUILD_ONLY = {
    "handlebars": Path("/usr/share/nodejs/handlebars"),
    "node-flatted": Path("/usr/share/nodejs/flatted"),
    "node-brace-expansion": Path("/usr/share/nodejs/brace-expansion"),
    "node-ip": Path("/usr/share/nodejs/ip"),
    "node-postcss": Path("/usr/share/nodejs/postcss"),
}
_REQUIRED_RUNTIME = (
    Path("/usr/bin/node"),
    Path("/usr/share/nodejs/undici/undici-fetch.js"),
    Path("/usr/share/nodejs/cjs-module-lexer/lexer.js"),
    Path("/usr/local/lib/node_modules/typescript/package.json"),
    Path("/opt/mmt/bin/runtime-a1-worker"),
)


class A18Refused(ValueError):
    """Fixed denial reasons only."""


def check_roots(
    prohibited: dict[str, Path] = _BUILD_ONLY,
    required: tuple[Path, ...] = _REQUIRED_RUNTIME,
) -> tuple[str, ...]:
    if set(prohibited) != set(_BUILD_ONLY):
        raise A18Refused("A18_PACKAGE_SCOPE_NOT_FIXED")
    for package, path in prohibited.items():
        if path != _BUILD_ONLY[package] or path.is_dir() or path.exists() or path.is_symlink():
            raise A18Refused("A18_BUILD_ONLY_MODULE_STILL_PRESENT")
    for path in required:
        if path not in _REQUIRED_RUNTIME or not path.is_file():
            raise A18Refused("A18_FIXED_RUNTIME_IMPORT_MISSING")
    return tuple(sorted(prohibited))


if __name__ == "__main__":
    checked = check_roots()
    print("CERT_A18_NO_BUILD_ONLY_IMPORT_ROOTS=" + str(len(checked)))
    print("CERT_A18_EXACT_PATH_ABSENCE_ONLY__NO_CVE_FIX_OR_RELEASE")
