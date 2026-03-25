# syntax=docker/dockerfile:1
# ===========================================================================
# ERC-7730 Analyzer — production image
#
# Bakes the full analyzer + screenshot pipeline into a single image:
#   - Python 3.12 via uv (managed install; no Debian python3 package)
#   - Node 20 + pnpm + device-sdk-ts (pre-built)
#   - Ethereum app .elf files baked from app-ethereum CI (default: stax + flex; build-time only)
#   - Native Speculos via the ``speculos`` PyPI package + qemu-user-static
#     (cs-tester uses --external-speculos; no Docker-in-Docker)
#
# Build (requires a token that can call the Actions API for app-ethereum artifacts;
# locally use a PAT with ``actions:read``; deploy CI uses ``github.token``):
#   docker build -t erc7730-analyzer \
#     --secret id=github_token,env=GITHUB_TOKEN .
#
# Optional: ``--build-arg APP_ETH_ARTIFACT_ID=<id>`` pins the artifact; ``--build-arg CS_ELF_DEVICES=stax,flex``
# controls which device trees are extracted from that zip (comma-separated).
#
# Run (service mode — default):
#   docker run --rm -p 8080:8080 --env-file .env erc7730-analyzer
#
# Run (CLI mode):
#   docker run --rm --env-file .env \
#     erc7730-analyzer cli --erc7730_file /data/descriptor.json
# ===========================================================================

# ======================== build args ========================
ARG DMK_REPO=Maroutis/device-sdk-ts
ARG DMK_REF=feat/external-speculos
ARG CS_DEVICE=stax
ARG UV_VERSION=0.11.0
ARG APP_ETH_ARTIFACT_ID=
ARG CS_ELF_DEVICES=stax,flex

# ---------- stage 1: build device-sdk-ts (public) ----------
FROM node:20-bookworm-slim AS dmk-builder

ARG DMK_REPO
ARG DMK_REF

RUN apt-get update -qq && apt-get install -qq -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g --progress=false --loglevel=warn pnpm@9

WORKDIR /build
RUN git clone --quiet --depth 1 --branch ${DMK_REF} \
        https://github.com/${DMK_REPO}.git . \
    && pnpm install --reporter=silent --no-color --frozen-lockfile \
    && pnpm build:libs

RUN printf '{\n  "repo": "%s",\n  "ref": "%s"\n}\n' \
        "${DMK_REPO}" "${DMK_REF}" \
    > .erc7730_analyzer_dmk_ready.json

# ---------- stage: fetch Ethereum app ELF (requires BuildKit secret github_token) ----------
FROM debian:bookworm-slim AS elf-fetcher

ARG APP_ETH_ARTIFACT_ID=
ARG CS_ELF_DEVICES=stax,flex

RUN apt-get update -qq \
    && apt-get install -qq -y --no-install-recommends ca-certificates python3 python3-requests \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /fetch
COPY src/utils/screenshots/elf_artifacts.py ./elf_artifacts.py

RUN mkdir -p /out

RUN --mount=type=secret,id=github_token \
    export GITHUB_TOKEN="$(tr -d '\n\r' </run/secrets/github_token)" && \
    if [ -n "${APP_ETH_ARTIFACT_ID}" ]; then \
      python3 elf_artifacts.py --output-root /out --devices "${CS_ELF_DEVICES}" --artifact-id "${APP_ETH_ARTIFACT_ID}"; \
    else \
      python3 elf_artifacts.py --output-root /out --devices "${CS_ELF_DEVICES}"; \
    fi

# ---------- uv binary provider (enables ARG expansion for the image tag) ----------
ARG UV_VERSION
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv-bin

# ---------- final image (single bookworm rootfs; tools from apt/repos) ----------
FROM debian:bookworm-slim

ARG CS_DEVICE=stax

WORKDIR /app

RUN apt-get update -qq \
    && apt-get install -qq -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        jq \
        qemu-user-static \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update -qq \
    && apt-get install -qq -y --no-install-recommends nodejs \
    && npm install -g --progress=false --loglevel=warn pnpm@9 \
    && rm -rf /var/lib/apt/lists/*

# Install uv by copying binaries from the official distroless image (documented at the URL above).
COPY --from=uv-bin /uv /uvx /bin/

ENV UV_PYTHON_PREFERENCE=only-managed
RUN uv python install 3.12

# ---------- Python deps ----------
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --no-progress --quiet

# ---------- Pre-built device-sdk-ts (artifact copy only) ----------
COPY --from=dmk-builder /build /data/screenshots/device-sdk-ts

# ---------- Baked Ethereum app ELF (from elf-fetcher stage) ----------
COPY --from=elf-fetcher /out /data/screenshots/ethereum-app-elfs

# ---------- Runtime config ----------
ENV PYTHONUNBUFFERED=1
ENV CS_TESTER_ROOT=/data/screenshots/device-sdk-ts
ENV ETH_APP_ELF_ROOT=/data/screenshots/ethereum-app-elfs
ENV CS_TESTER_DEVICE=${CS_DEVICE}

EXPOSE 8080

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["service"]
