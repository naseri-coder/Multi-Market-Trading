"""Static regression checks for the current production container layout."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = PROJECT_ROOT / "Dockerfile.production"


def dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def test_production_image_is_digest_pinned_in_both_stages() -> None:
    dockerfile = dockerfile_text()
    pinned = (
        "FROM python:3.12-slim@sha256:"
        "f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"
    )

    assert dockerfile.count(pinned) == 2


def test_runtime_dependencies_are_hash_locked_and_copied_to_site_packages() -> None:
    dockerfile = dockerfile_text()

    assert "COPY requirements.hashed.lock ./" in dockerfile
    assert "--require-hashes --target=/install" in dockerfile
    assert (
        "COPY --from=builder /install /usr/local/lib/python3.12/site-packages"
        in dockerfile
    )


def test_runtime_uses_current_production_source_layout_and_non_root_user() -> None:
    dockerfile = dockerfile_text()
    workdir = "WORKDIR /opt/crypto-signal-bot"
    app_copy = "COPY production_source/app ./app"

    assert workdir in dockerfile
    assert app_copy in dockerfile
    assert "COPY production_source/migrations ./migrations" in dockerfile
    assert "COPY production_source/alembic.ini ./alembic.ini" in dockerfile
    assert dockerfile.index(workdir) < dockerfile.index(app_copy)
    assert "adduser --disabled-password" in dockerfile
    assert "--uid 10001" in dockerfile
    assert "USER bot" in dockerfile
