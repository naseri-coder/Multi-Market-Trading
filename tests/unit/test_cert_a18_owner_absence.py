"""CERT-A18 mock-only tests for proven Debian owner path absence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deploy.runtime_a2 import a18_build_only_guard as guard
from scripts import ci_cert_a18_owner_absence as a18

_ROOT = Path(__file__).resolve().parents[2]
_BASE = "sha256:" + "a" * 64
_CANDIDATE = "sha256:" + "b" * 64


def _set(tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    base = {f"usr/share/doc/generic/file-{i}" for i in range(60)}
    candidate = set(base)
    candidate.update((
        "usr/bin/node",
        "opt/mmt/bin/runtime-a1-worker",
        "usr/share/nodejs/undici/undici-fetch.js",
        "usr/local/lib/node_modules/typescript/package.json",
    ))
    base.update(candidate)
    for package, (_, prefix) in a18._PACKAGES.items():
        code_path = prefix + "index.js"
        base.add(code_path)
        (manifests / f"{package}.list").write_text("/.\n/" + code_path + "\n")
    base_tree, lean_tree = tmp_path / "base.txt", tmp_path / "candidate.txt"
    base_tree.write_text("\n".join(sorted(base)) + "\n")
    lean_tree.write_text("\n".join(sorted(candidate)) + "\n")
    return manifests, base_tree, lean_tree


def _check(tmp_path, *, root=_ROOT):
    return a18.prove(root, *_set(tmp_path), _BASE, _CANDIDATE)


def test_proven_module_paths_are_absent_but_no_vulnerabilities_closed(tmp_path):
    result = _check(tmp_path)
    assert result["owned_modules_examined"] == 5
    assert result["owned_code_paths_absent_from_candidate"] == 5
    assert len(result["package_results"]) == 5
    assert {x["package"] for x in result["package_results"]} == set(a18._PACKAGES)
    for row in result["package_results"]:
        assert row["original_owned_code_paths_present_in_candidate"] == 0
        assert row["status"] == "EXACT_OWNER_CODE_PATHS_ABSENT_ONLY_REVIEW_OPEN"
        assert row["fix_from_vendor_authenticated"] is False
        assert row["advisories_closed"] == 0
    assert result["all_199_original_findings_remain_open"] is True
    assert result["other_code_locations_and_vulnerable_bundled_copies_not_excluded"]
    assert result["worker_execution_authorized"] is False
    assert result["production_authorized"] is False
    assert result["publisher_signature_independently_verified"] is False
    assert len(result["report_sha256"]) == 64


def test_any_surviving_js_path_blocks_claim(tmp_path):
    manifests, base_tree, lean_tree = _set(tmp_path)
    path = "usr/share/nodejs/handlebars/index.js"
    with lean_tree.open("a") as handle:
        handle.write(path + "\n")
    with pytest.raises(a18.A18Refused, match="A18_ORIGINAL_CODE_PATH_PRESENT"):
        a18.prove(_ROOT, manifests, base_tree, lean_tree, _BASE, _CANDIDATE)


def test_absent_original_debian_code_is_not_proof(tmp_path):
    manifests, base_tree, lean_tree = _set(tmp_path)
    lines = base_tree.read_text().splitlines()
    base_tree.write_text("\n".join(
        line for line in lines
        if line != "usr/share/nodejs/handlebars/index.js"
    ) + "\n")
    with pytest.raises(a18.A18Refused, match="A18_ORIGINAL_DPKG_CODE_NOT_IN_BASE"):
        a18.prove(_ROOT, manifests, base_tree, lean_tree, _BASE, _CANDIDATE)


@pytest.mark.parametrize("mutation", [
    lambda s: s.update({"usr/share/nodejs/undici/undici-fetch.js"}),
    lambda s: s.update({"usr/bin/node"}),
    lambda s: s.update({"opt/mmt/bin/runtime-a1-worker"}),
])
def test_required_module_presence_is_checked(tmp_path, mutation):
    manifests, base_tree, lean_tree = _set(tmp_path)
    removed = set()
    mutation(removed)
    lean_tree.write_text("\n".join(sorted(
        set(lean_tree.read_text().splitlines()) - removed
    )) + "\n")
    with pytest.raises(a18.A18Refused, match="A18_REQUIRED_NODE_RUNTIME_DISAPPEARED"):
        a18.prove(_ROOT, manifests, base_tree, lean_tree, _BASE, _CANDIDATE)


@pytest.mark.parametrize("version", [
    "0.0.0", "", "4.7.7", "2.0.1-3",
])
def test_version_drift_fails_closed(tmp_path, version):
    root = tmp_path / "replica"
    lock = root / "deploy/runtime_a2"
    lock.mkdir(parents=True)
    original = json.loads((_ROOT / "deploy/runtime_a2/a11_apt_closure.json").read_text())
    for entry in original["packages"]:
        if entry["package"] == "handlebars":
            entry["version"] = version
    (lock / "a11_apt_closure.json").write_text(json.dumps(original))
    manifests, baseline, lean = _set(tmp_path)
    with pytest.raises(a18.A18Refused, match="A18_BUILD_ONLY_PACKAGE_LOCK_VERSION_DRIFT"):
        a18.prove(root, manifests, baseline, lean, _BASE, _CANDIDATE)


def test_hardlink_or_symlinked_manifest_is_refused(tmp_path):
    manifests, base_tree, lean_tree = _set(tmp_path)
    target = manifests / "handlebars.list"
    other = manifests / "handlebars-real.list"
    other.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(other)
    with pytest.raises(a18.A18Refused, match="A18_INPUT_SYMLINK_REFUSED"):
        a18.prove(_ROOT, manifests, base_tree, lean_tree, _BASE, _CANDIDATE)


def test_unsafe_path_component_refused(tmp_path):
    manifests, base_tree, lean_tree = _set(tmp_path)
    with base_tree.open("a") as handle:
        handle.write("../forged.js\n")
    with pytest.raises(a18.A18Refused, match="A18_UNSAFE_TAR_OR_DPKG_PATH"):
        a18.prove(_ROOT, manifests, base_tree, lean_tree, _BASE, _CANDIDATE)


def test_wrong_or_duplicate_image_id_denied(tmp_path):
    manifests, baseline, lean = _set(tmp_path)
    for first, second in [
        ("local:latest", _CANDIDATE),
        (_BASE, _BASE),
        (_BASE, "sha256:INVALID"),
    ]:
        with pytest.raises(a18.A18Refused, match="A18_DOCKER_IMAGE_ID_INVALID"):
            a18.prove(_ROOT, manifests, baseline, lean, first, second)


def test_build_guard_denies_build_only_tree_present(tmp_path):
    prohibited = {
        name: tmp_path / name for name in guard._BUILD_ONLY
    }
    required = tuple(tmp_path / f"needed-{i}" for i in range(5))
    for path in required:
        path.write_text("fixed")
    # Explicit fail-closed: scope cannot be replaced by an invented smaller set.
    with pytest.raises(guard.A18Refused, match="A18_BUILD_ONLY_MODULE_STILL_PRESENT"):
        guard.check_roots(prohibited, required)
    with pytest.raises(guard.A18Refused, match="A18_PACKAGE_SCOPE_NOT_FIXED"):
        guard.check_roots({"handlebars": prohibited["handlebars"]}, required)
    assert len(guard._BUILD_ONLY) == 5
    assert all(path.is_absolute() for path in guard._BUILD_ONLY.values())


def test_dockerfile_does_not_replace_main_worker_or_install_dependencies():
    d = (_ROOT / "deploy/runtime_a2/Dockerfile.a18-absence").read_text()
    lines = [line for line in d.splitlines() if line.startswith("FROM ")]
    assert lines == [
        "FROM mmt/runtime-a15-lean:pr AS a18-checked-local-lean",
        "FROM mmt/runtime-a15-lean:pr",
    ]
    assert "RUN python -I /opt/mmt/a18_build_only_guard.py" in d
    revalidated_copy = (
        "COPY --from=a18-checked-local-lean "
        "/opt/mmt/bin/runtime-a1-worker /opt/mmt/bin/runtime-a1-worker"
    )
    assert revalidated_copy in d
    assert (
        d.index("RUN python -I /opt/mmt/a18_build_only_guard.py")
        < d.index("COPY --from=a18-checked-local-lean")
    )
    assert 'ENTRYPOINT ["/opt/mmt/bin/runtime-a1-worker"]' in d
    assert "USER 65534:65534" in d
    for text in ("apt-get", "npm install", "pip install", "--privileged"):
        assert text not in d
    ignore = (_ROOT / "deploy/runtime_a2/Dockerfile.a18-absence.dockerignore")
    assert ignore.read_text().splitlines() == [
        "# CERT-A18 dedicated fixed build context; no code/user files or secrets.",
        "**", "!deploy/", "!deploy/runtime_a2/",
        "!deploy/runtime_a2/a18_build_only_guard.py",
    ]


def test_no_user_payload_or_docker_execution_inside_offline_analyzer():
    source = (_ROOT / "scripts/ci_cert_a18_owner_absence.py").read_text()
    for disallowed in (
        "docker run", "docker exec", "subprocess.run(",
        "docker build", "urllib.request", "requests.get(",
    ):
        assert disallowed not in source
