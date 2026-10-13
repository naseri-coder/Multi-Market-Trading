# Nonproduction image candidate; do not use on a sensitive host.
# On independent review replace base image tag with verified immutable digest.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NODE_PATH=/usr/local/lib/node_modules

RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global --ignore-scripts typescript@5.9.3 \
    && python -m pip install --no-cache-dir wasmtime==49.0.0

COPY --chmod=0555 scripts/runtime_a2_worker.py /opt/mmt/bin/runtime-a1-worker

USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["/opt/mmt/bin/runtime-a1-worker"]
