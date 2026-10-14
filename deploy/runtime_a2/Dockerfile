# CERT-A10 nonproduction-only fixed linux/amd64 archive candidate.
# Digest pins are *content equality*, NOT upstream identity or gVisor attestation.
# APT .deb archive bytes are pinned; mutable Debian mirrors and signatures
# are NOT independently frozen/attested. Fail closed on any archive drift.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NODE_PATH=/usr/local/lib/node_modules

# Exact 372-entry Debian archive closure is validated BEFORE installation.
# Download into a separate APT cache so Docker apt.conf post-hooks cannot
# silently remove the bytes prior to hash verification.
COPY deploy/runtime_a2/a11_apt_closure.py /opt/mmt/a11_apt_closure.py
COPY deploy/runtime_a2/a11_apt_closure.json /opt/mmt/a11_apt_closure.json
RUN mkdir -p /tmp/mmt-a11-apt/archives/partial \
    && apt-get update \
    && apt-get -y -o Dir::Cache::archives=/tmp/mmt-a11-apt/archives \
        install --download-only --no-install-recommends nodejs npm \
    && python /opt/mmt/a11_apt_closure.py verify \
    && apt-get -y -o Dir::Cache::archives=/tmp/mmt-a11-apt/archives \
        install --no-download --no-install-recommends nodejs npm \
    && python /opt/mmt/a11_apt_closure.py installed \
    && rm -rf /tmp/mmt-a11-apt /var/lib/apt/lists/* \
    && rm -f /opt/mmt/a11_apt_closure.py /opt/mmt/a11_apt_closure.json

# Download only the exact fixed TypeScript npm archive and verify SHA-512
# BEFORE running npm. Offline npm cannot silently fetch more dependencies.
RUN python -c 'import hashlib,pathlib,sys,urllib.request; url="https://registry.npmjs.org/typescript/-/typescript-5.9.3.tgz"; data=urllib.request.urlopen(url,timeout=30).read(30000001); (0<len(data)<=30000000 and hashlib.sha512(data).hexdigest()=="8e5d6f6733c38a72ebf5e52ddc9feded5e8580d130f508ef04f772b33f4a7d00c3e357d0ac2d98e2f290762694a454f86d795bd511e12e9a7cc2d9ba3394e04b") or sys.exit("A10_TS_ARCHIVE_SHA512_MISMATCH"); pathlib.Path("/tmp/typescript-5.9.3.tgz").write_bytes(data)' \
    && npm install --global --ignore-scripts --offline --no-audit --no-fund /tmp/typescript-5.9.3.tgz \
    && rm -f /tmp/typescript-5.9.3.tgz

# Pip must verify the *exact* linux/amd64 Wasmtime wheel SHA-256.
COPY deploy/runtime_a2/a10_wasmtime.lock /tmp/a10_wasmtime.lock
RUN python -m pip install --no-cache-dir --no-deps --only-binary=:all: \
      --require-hashes -r /tmp/a10_wasmtime.lock \
    && rm -f /tmp/a10_wasmtime.lock

COPY --chmod=0555 scripts/runtime_a2_worker.py /opt/mmt/bin/runtime-a1-worker

USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["/opt/mmt/bin/runtime-a1-worker"]
