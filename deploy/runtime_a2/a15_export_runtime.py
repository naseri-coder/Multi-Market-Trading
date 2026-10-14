"""CERT-A15 fixed, harmless, no-network export of runtime files from A2 image.

RUN ONLY inside the GitHub-hosted, existing CERT-A12-pinned A2 candidate.
This is an experiment, NOT a trustworthy signed runtime supply chain.
The exported shared libraries are not independently ABI/provenance certified.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
from pathlib import Path

_ROOTFS = Path("/opt/mmt/a15-rootfs")
_NODE = Path("/usr/bin/node")
_TS = Path("/usr/local/lib/node_modules/typescript")
_WASM = Path("/usr/local/lib/python3.12/site-packages/wasmtime")
_WORKER = Path("/opt/mmt/bin/runtime-a1-worker")
_LIB_RE = re.compile(r"(?<![A-Za-z0-9])(/[^\s()]+)")
_ALLOWED_LIB_ROOTS = ("/lib/", "/lib64/", "/usr/lib/")


class A15ExportRefused(ValueError):
    """Only fixed error codes, never input controlled paths."""


def _copy_file(source: Path, root: Path) -> dict[str, str]:
    if (not source.is_absolute() or not source.is_file()
            or source.is_dir()):
        raise A15ExportRefused("A15_REQUIRED_SOURCE_FILE_ABSENT")
    # /lib is a symlink to /usr/lib on Debian. Resolve the DIRECTORY but
    # keep the requested filename (SONAME, e.g. libuv.so.1). Resolving the
    # entire symlink replaces libuv.so.1 with libuv.so.1.0.0 and breaks Node.
    # The /lib64 dynamic loader is already a link in the pinned base:
    # copy its real target to avoid Docker's file-to-symlink collision.
    parent = source.parent.resolve(strict=True)
    if source.parts[1] in {"lib", "lib64"} and not str(parent).startswith(
        "/usr/lib"
    ):
        raise A15ExportRefused("A15_LIBRARY_RESOLUTION_OUTSIDE_USR_LIB")
    exported = source.resolve(strict=True) if source.parts[1] == "lib64" else (
        parent / source.name
    )
    target = root / exported.relative_to("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target, follow_symlinks=True)
    if target.stat().st_size != source.stat().st_size:
        raise A15ExportRefused("A15_EXPORT_FILE_SIZE_MISMATCH")
    digest = hashlib.file_digest(source.open("rb"), "sha256").hexdigest()
    if hashlib.file_digest(target.open("rb"), "sha256").hexdigest() != digest:
        raise A15ExportRefused("A15_EXPORTED_BYTES_CHANGED")
    return {"path": "/" + str(source.relative_to("/")), "sha256": digest}


def _node_dependencies() -> list[Path]:
    """Traverse the fixed Node ELF ldd closure, including libnode's dependencies.

    ldd /usr/bin/node alone is insufficient: libuv.so.1 is brought in by
    libnode.so.108 and may not appear in the executable's direct ldd lines.
    Every inspected file must originate from the pinned local A2 image.
    """
    pending = [_NODE]
    visited: set[Path] = set()
    deps: set[Path] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        if len(visited) > 121:
            raise A15ExportRefused("A15_ELF_CLOSURE_TOO_LARGE")
        # The pinned base already contains the loader; ldd on the loader
        # itself is not guaranteed to return dependencies consistently.
        if current != _NODE and current.name.startswith("ld-linux-"):
            continue
        try:
            response = subprocess.run(
                ("/usr/bin/ldd", str(current)), timeout=8,
                capture_output=True, check=False, stdin=subprocess.DEVNULL,
                close_fds=True, shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise A15ExportRefused("A15_LDD_FAILED") from exc
        if (response.returncode != 0 or not 0 < len(response.stdout) <= 20_000
                or b"not found" in response.stdout):
            raise A15ExportRefused("A15_UNRESOLVED_NODE_RUNTIME_LIBRARIES")
        try:
            lines = response.stdout.decode("ascii").splitlines()
        except UnicodeError as exc:
            raise A15ExportRefused("A15_LDD_ENCODING_INVALID") from exc
        for line in lines:
            for literal in _LIB_RE.findall(line):
                if not literal.startswith(_ALLOWED_LIB_ROOTS):
                    raise A15ExportRefused("A15_DEPENDENCY_OUTSIDE_SYSTEM_LIBRARY")
                path = Path(literal)
                if not path.is_file():
                    raise A15ExportRefused("A15_LIBRARY_PATH_NOT_FOUND")
                if path not in deps:
                    deps.add(path)
                    pending.append(path)
                if len(deps) > 120:
                    raise A15ExportRefused("A15_ELF_CLOSURE_TOO_LARGE")
    if len(deps) < 3:
        raise A15ExportRefused("A15_NODE_DEPENDENCY_CLOSURE_INVALID")
    if not any("libnode" in item.name for item in deps):
        raise A15ExportRefused("A15_EXPECTED_LIBNODE_MISSING")
    return sorted(deps)

def export_fixed_runtime(root: Path = _ROOTFS) -> dict:
    if root != _ROOTFS or root.is_symlink() or root.exists():
        raise A15ExportRefused("A15_FIXED_EMPTY_DESTINATION_REQUIRED")
    if importlib.metadata.version("wasmtime") != "49.0.0":
        raise A15ExportRefused("A15_WASMTIME_VERSION_DRIFT")
    try:
        node = subprocess.run(
            (str(_NODE), "--version"), timeout=4,
            stdin=subprocess.DEVNULL, capture_output=True, check=False,
            close_fds=True, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise A15ExportRefused("A15_NODE_VERSION_QUERY_FAILED") from exc
    if node.returncode != 0 or node.stdout.strip() != b"v18.20.4":
        raise A15ExportRefused("A15_NODE_VERSION_NOT_PINNED")
    if not _TS.is_dir() or not _WASM.is_dir():
        raise A15ExportRefused("A15_TYPESCRIPT_OR_WASMTIME_MISSING")
    package = json.loads((_TS / "package.json").read_text(encoding="utf-8"))
    if type(package) is not dict or package.get("version") != "5.9.3":
        raise A15ExportRefused("A15_TYPESCRIPT_VERSION_DRIFT")
    dist = Path("/usr/local/lib/python3.12/site-packages/wasmtime-49.0.0.dist-info")
    if not dist.is_dir():
        raise A15ExportRefused("A15_WASMTIME_METADATA_MISSING")
    deps = _node_dependencies()
    root.mkdir(parents=True, exist_ok=False)
    observed = [_copy_file(path, root) for path in [_NODE, _WORKER, *deps]]
    for directory in (_TS, _WASM, dist):
        target = root / directory.relative_to("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(directory, target, symlinks=False)
    report = {
        "schema": 1,
        "status": "CERT_A15_LOCAL_A2_RUNTIME_EXPORT_UNATTESTED",
        "node_version": "18.20.4",
        "typescript_version": "5.9.3",
        "wasmtime_version": "49.0.0",
        "copied_node_shared_libraries": len(deps),
        "copied_runtime_file_hashes": observed,
        "npm_runtime_cli_included": False,
        "original_apt_372_lock_changed": False,
        "worker_execution_authorized": False,
        "gvisor_certified": False,
        "production_authorized": False,
    }
    report_path = root / "opt/mmt/a15-runtime-inventory.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    data = export_fixed_runtime()
    print("A15_NODE_DEPENDENCY_LIBS=" + str(data["copied_node_shared_libraries"]))
    print("A15_EXPORT_UNATTESTED_NEVER_RELEASED")
