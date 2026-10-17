"""Stage 3H: build/install/test a demo-only Wheel without trusting its release status.

Source: unchanged exact Git commit on a separate experimental branch.
No release signing, tag, merge, network provider, Telegram, real trade, or prod.
"""
from __future__ import annotations

import ast
import configparser
import hashlib
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import textwrap
import venv
import zipfile
from pathlib import Path

BASE = "7bbb3541fb6d63f960bee9f197fe026ed6d04608"
BRANCH = "ci/stage3h-offline-demo-wheel-20261017"
EXPERIMENT_FILES = {
    ".github/workflows/stage3h-isolated-demo-wheel.yml",
    "scripts/ci_stage3h_isolated_demo_wheel.py",
    "docs/MMT_V0_4_0_STAGE3H_OFFLINE_DEMO_WHEEL_EXPERIMENT.md",
}
MODULES = frozenset({
    "__init__", "a21_custom_contract", "brooks_paper_receipts",
    "brooks_replay", "contracts", "custom_cli", "delivery_ledger",
    "engine_control_store", "engine_plan", "external_abi",
    "futures_pairs", "futures_venues", "iran_futures_eligibility",
    "paper_demo_cli_v1", "public_demo_custom_worker", "quotes",
    "registry", "routing", "trusted_custom",
})
CONSOLES = {
    "naseri-brooks-replay": "naseri_markets.brooks_replay:main",
    "naseri-paper-demo": "naseri_markets.paper_demo_cli_v1:main",
}
FORBIDDEN_PY = {
    "brooks_market_feed", "brooks_kraken_feed", "brooks_paper_service",
    "bot_admin_app", "platform_cli", "installed_paper_pilot_stage10_v1",
    "bybit", "binance_futures",
}
NO_NETWORK_IMPORT_ROOTS = {
    "socket", "httpx", "requests", "aiohttp", "urllib3", "websocket",
    "ftplib", "telnetlib", "telegram", "ccxt",
}
NO_NETWORK_IMPORTS = {"urllib.request", "http.client"}
EPOCH = "1790000000"
PACKAGE = "multi-market-trading-offline-demo"
WHEEL_VERSION = "0.4.0rc1"


def check(cmd, *, cwd=None, env=None):
    return subprocess.check_output(
        cmd, cwd=cwd, env=env, stderr=subprocess.STDOUT, text=True,
    ).strip()


def refuse(label):
    raise RuntimeError("STAGE3H_REFUSED_" + label)


def _validate_source(repo):
    if check(["git", "rev-parse", "HEAD"], cwd=repo) == BASE:
        refuse("EXPERIMENT_BRANCH_REQUIRED")
    if check(["git", "rev-parse", "HEAD^"], cwd=repo) != BASE:
        refuse("WRONG_EXPERIMENT_BASE")
    if check(["git", "branch", "--show-current"], cwd=repo) != BRANCH:
        refuse("WRONG_EXPERIMENT_BRANCH")
    if check(["git", "status", "--porcelain"], cwd=repo):
        refuse("DIRTY_EXPERIMENT_WORKTREE")
    changed = set(check([
        "git", "diff", "--name-only", BASE, "HEAD",
    ], cwd=repo).splitlines())
    if changed != EXPERIMENT_FILES:
        refuse("EXPERIMENT_CHANGED_UNAPPROVED_SOURCES")
    original = check(["git", "rev-parse", BASE + ":naseri_markets"], cwd=repo)
    unchanged = check(["git", "rev-parse", "HEAD:naseri_markets"], cwd=repo)
    if original != unchanged:
        refuse("PRODUCT_SOURCE_TREE_CHANGED")
    actual = {p.stem for p in (repo / "naseri_markets").glob("*.py")}
    if not MODULES.issubset(actual):
        refuse("ALLOWLIST_SOURCE_MISSING")
    if not FORBIDDEN_PY.isdisjoint(MODULES):
        refuse("RISKY_MODULE_IN_ALLOWLIST")
    if len(MODULES) != 19 or len(CONSOLES) != 2:
        refuse("EXACT_MODULE_AND_CLI_COUNT")
    return original


def _validate_imports(raw, module):
    tree = ast.parse(raw, filename=module)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 1:
                if node.module is None:
                    refuse("DYNAMIC_RELATIVE_IMPORT")
                names = ["naseri_markets." + node.module]
            elif node.level != 0:
                refuse("MULTILEVEL_RELATIVE_IMPORT")
            else:
                names = [node.module or ""]
        else:
            continue
        for name in names:
            if name in NO_NETWORK_IMPORTS or name.split(".")[0] in NO_NETWORK_IMPORT_ROOTS:
                refuse("NETWORK_OR_TELEGRAM_IMPORT_" + module)
            if name.startswith("naseri_markets."):
                target = name.removeprefix("naseri_markets.").split(".")[0]
                if target not in MODULES:
                    refuse("UNAPPROVED_MODULE_DEPENDENCY_" + module)


def _stage(repo, root):
    parent = root / "stages"
    parent.mkdir(mode=0o700)
    contexts = []
    hashes = {}
    for n in ("first", "second"):
        context = parent / n
        package_dir = context / "naseri_markets"
        package_dir.mkdir(parents=True)
        for module in sorted(MODULES):
            file = "naseri_markets/" + module + ".py"
            raw = (repo / file).read_bytes()
            # A branch tip cannot secretly alter a source file and get the
            # same canonical Git-tree hash (checked above).
            _validate_imports(raw, module)
            digest = hashlib.sha256(raw).hexdigest()
            if module in hashes and hashes[module] != digest:
                refuse("SOURCE_CHANGED_BETWEEN_STAGES")
            hashes[module] = digest
            (package_dir / (module + ".py")).write_bytes(raw)
        context.joinpath("pyproject.toml").write_text(textwrap.dedent("""
            [build-system]
            requires = ["setuptools==80.9.0", "wheel==0.45.1"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "multi-market-trading-offline-demo"
            version = "0.4.0rc1"
            description = "ISOLATED TEST ONLY: offline Brooks replay and public toy PAPER"
            requires-python = ">=3.12,<3.13"
            dependencies = []

            [project.scripts]
            naseri-brooks-replay = "naseri_markets.brooks_replay:main"
            naseri-paper-demo = "naseri_markets.paper_demo_cli_v1:main"

            [tool.setuptools.packages.find]
            where = ["."]
            include = ["naseri_markets"]
            exclude = ["naseri_markets.*"]
        """).lstrip(), encoding="utf-8")
        context.joinpath("README.md").write_text(
            "Non-published isolated OFFLINE demo Wheel — NOT the v0.4.0 release. "
            "No approved live market data, broker trades or Telegram.\n",
            encoding="utf-8",
        )
        shutil.copyfile(repo / "LICENSE", context / "LICENSE")
        contexts.append(context)
    return contexts, hashes


def _build(contexts, root):
    wheels = []
    env = os.environ.copy()
    env.update({"SOURCE_DATE_EPOCH": EPOCH, "PYTHONDONTWRITEBYTECODE": "1"})
    for i, context in enumerate(contexts):
        destination = root / ("wheels" + str(i))
        destination.mkdir(mode=0o700)
        subprocess.run([
            sys.executable, "-m", "pip", "wheel", "--no-deps",
            "--no-index", "--no-build-isolation", "--wheel-dir", str(destination),
            str(context),
        ], env=env, check=True, stdout=subprocess.DEVNULL)
        output = list(destination.glob("*.whl"))
        if len(output) != 1:
            refuse("WHEEL_COUNT")
        wheels.append(output[0])
    raw = [p.read_bytes() for p in wheels]
    if raw[0] != raw[1]:
        refuse("TWO_WHEELS_NOT_BYTE_IDENTICAL")
    return wheels[0], hashlib.sha256(raw[0]).hexdigest()


def _verify_wheel(wheel):
    with zipfile.ZipFile(wheel) as f:
        names = f.namelist()
        source_members = {
            n.removeprefix("naseri_markets/").removesuffix(".py")
            for n in names
            if n.startswith("naseri_markets/") and n.endswith(".py")
            and n.count("/") == 1
        }
        if source_members != MODULES:
            refuse("ACTUAL_PACKED_SOURCE_NOT_ALLOWLIST")
        if any("production_source" in n or "private" in n.lower()
               for n in names):
            refuse("PRIVATE_OR_LEGACY_SOURCE_BUNDLED")
        ep = [n for n in names if n.endswith(".dist-info/entry_points.txt")]
        if len(ep) != 1:
            refuse("WHEEL_ENTRYPOINT_METADATA_COUNT")
        cfg = configparser.ConfigParser()
        cfg.optionxform = str
        cfg.read_string(f.read(ep[0]).decode("utf-8"))
        if dict(cfg.items("console_scripts")) != CONSOLES:
            refuse("WHEEL_ENTRYPOINT_SET_DRIFT")
        if any("/scripts/" in n or n.endswith(".so") for n in names):
            refuse("UNEXPECTED_EXECUTABLE_PAYLOAD")
    print("STAGE3H_REPRODUCIBLE_19_MODULE_TWO_CLI_WHEEL_PASS")


def _validate_installed(venv_root, wheel):
    venv.EnvBuilder(with_pip=True, clear=True).create(venv_root)
    interpreter = venv_root / "bin" / "python"
    subprocess.run([
        str(interpreter), "-m", "pip", "install", "--no-index",
        "--no-deps", str(wheel),
    ], check=True, stdout=subprocess.DEVNULL)
    check_script = textwrap.dedent("""
        import importlib.metadata as md
        import importlib.util as util
        import json
        import shutil

        dist = md.distribution("multi-market-trading-offline-demo")
        assert dist.version == "0.4.0rc1"
        actual = {ep.name: ep.value for ep in dist.entry_points
                  if ep.group == "console_scripts"}
        expected = {
            "naseri-brooks-replay": "naseri_markets.brooks_replay:main",
            "naseri-paper-demo": "naseri_markets.paper_demo_cli_v1:main",
        }
        assert actual == expected, actual
        assert all(shutil.which(key) for key in expected)
        for key in (
            "naseri-brooks-market", "naseri-brooks-kraken-paper",
            "naseri-brooks-paper-service", "naseri-engine-admin",
            "naseri-custom", "naseri-markets", "naseri-paper-pilot",
        ):
            assert shutil.which(key) is None, key
        for module in (
            "naseri_markets.brooks_market_feed",
            "naseri_markets.brooks_kraken_feed",
            "naseri_markets.brooks_paper_service",
            "naseri_markets.bot_admin_app",
            "naseri_markets.installed_paper_pilot_stage10_v1",
        ):
            assert util.find_spec(module) is None, module
        import naseri_markets.brooks_replay
        import naseri_markets.paper_demo_cli_v1
        print("STAGE3H_INSTALLED_TWO_ENTRYPOINT_ONLY_PASS")
    """)
    env = os.environ.copy()
    env["PATH"] = str(venv_root / "bin") + os.pathsep + os.environ.get("PATH", "")
    subprocess.run([str(interpreter), "-I", "-c", check_script], env=env, check=True)
    return interpreter


def _deny_network_end_to_end(python, root):
    script = root / "execute_offline_without_network.py"
    script.write_text(textwrap.dedent("""
        import json
        import os
        import pathlib
        import subprocess
        import sys

        runtime = pathlib.Path(sys.argv[1])
        bin_dir = pathlib.Path(sys.argv[2])
        environ = {
            "PATH": str(bin_dir) + ":/usr/bin:/bin",
            "HOME": str(runtime),
            "MMT_NONPRODUCTION": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        def call(args):
            p = subprocess.run(
                args, check=True, capture_output=True, text=True,
                timeout=30, env=environ, cwd=runtime,
            )
            return p.stdout.strip()

        assert call([str(bin_dir / "naseri-brooks-replay"), "--help"])
        assert call([str(bin_dir / "naseri-paper-demo"), "--help"])
        destination = runtime / "sample-state"
        init = json.loads(call([
            str(bin_dir / "naseri-paper-demo"), "--state-dir",
            str(destination), "init", "--ack-reviewed-public-toy",
        ]))
        assert init["action"] == "INITIALIZED_DISABLED"
        assert init["enabled"] is False
        assert init["broker_order_sent"] is False
        assert init["telegram_sent"] is False
        enabled = json.loads(call([
            str(bin_dir / "naseri-paper-demo"), "--state-dir",
            str(destination), "enable", "--revision", "1",
            "--descriptor-sha256", init["descriptor_sha256"],
        ]))
        assert enabled["action"] == "EXPLICITLY_ENABLED_PAPER_ONLY"
        replay = json.loads(call([
            str(bin_dir / "naseri-paper-demo"), "--state-dir",
            str(destination), "replay", "--ack-offline-replay",
        ]))
        assert replay["action"] == "OFFLINE_REPLAY"
        assert replay["broker_order_sent"] is False
        assert replay["telegram_sent"] is False
        assert replay["release_authorized"] is False
        inspected = json.loads(call([
            str(bin_dir / "naseri-paper-demo"), "--state-dir",
            str(destination), "inspect",
        ]))
        assert inspected["action"] == "READ_PAPER_HISTORY"
        assert inspected["paper_signal_count"] >= 1
        print("STAGE3H_NETNS_OFFLINE_TOY_PAPER_RESTART_PASS")
    """), encoding="utf-8")
    script.chmod(0o600)
    runtime = root / "runtime"
    runtime.mkdir(mode=0o700)
    username = pwd.getpwuid(os.getuid()).pw_name
    if not shutil.which("sudo") or not shutil.which("unshare"):
        refuse("NETNS_REQUIRED_TO_PROVE_NO_EGRESS")
    # Requires the default sudo permissions of an ephemeral Ubuntu GH runner.
    # If namespace creation is disallowed, report BLOCKED rather than falling
    # back to network-connected tests or claiming an isolation proof.
    cmd = [
        "sudo", "-n", "unshare", "--net", "--",
        "runuser", "-u", username, "--", "env", "-i",
        "PATH=" + str(python.parent) + ":/usr/bin:/bin",
        "HOME=" + str(runtime), "MMT_NONPRODUCTION=1",
        "PYTHONDONTWRITEBYTECODE=1", str(python), str(script),
        str(runtime), str(python.parent),
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("STAGE3H_NETNS_RUN_FAILED") from exc
    if p.returncode:
        # Never infer safety from partial execution or missing kernel support.
        print("STAGE3H_NETNS_EXECUTION_REFUSED; output redacted")
        refuse("NO_SUCCESSFUL_NO_NETWORK_RUNTIME_PROOF")
    if "STAGE3H_NETNS_OFFLINE_TOY_PAPER_RESTART_PASS" not in p.stdout:
        refuse("NETNS_MISSING_EXPLICIT_ACCEPTANCE")
    print("STAGE3H_NETNS_OFFLINE_TOY_PAPER_RESTART_PASS")


def main():
    if sys.version_info[:2] != (3, 12):
        refuse("CPYTHON_312_REQUIRED")
    repo = Path(__file__).resolve().parents[1]
    source_tree_sha = _validate_source(repo)
    with tempfile.TemporaryDirectory(prefix="mmt-stage3h-disposable-") as raw:
        root = Path(raw)
        root.chmod(0o700)
        contexts, hashes = _stage(repo, root)
        wheel, digest = _build(contexts, root)
        _verify_wheel(wheel)
        interpreter = _validate_installed(root / "venv", wheel)
        _deny_network_end_to_end(interpreter, root)
    print(json.dumps({
        "verdict": "STAGE3H_EXPERIMENT_ONLY_NOT_RELEASE_AUTHORIZED",
        "base_source_commit": BASE,
        "unchanged_source_subtree": source_tree_sha,
        "source_python_files": len(hashes),
        "console_scripts": sorted(CONSOLES),
        "two_builds_identical": True,
        "test_wheel_sha256": digest,
        "original_wheel_or_source_modified": False,
        "network_isolation_runtime_proof": True,
        "independently_approved_release_scope": False,
        "real_publisher_signature": False,
        "public_release_authorized": False,
        "merge_authorized": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
