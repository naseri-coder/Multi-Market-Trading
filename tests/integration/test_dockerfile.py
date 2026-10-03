"""Static regression checks for the production container layout."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_dependencies_are_copied_to_python_site_packages() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "python -m pip install --target=/install" in dockerfile
    assert "COPY --from=builder /install /usr/local/lib/python3.12/site-packages" in dockerfile


def test_runtime_workdir_contains_the_app_package() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    workdir = "WORKDIR /opt/crypto-signal-bot"
    app_copy = "COPY --chown=bot:bot app ./app"

    assert workdir in dockerfile
    assert app_copy in dockerfile
    assert dockerfile.index(workdir) < dockerfile.index(app_copy)
