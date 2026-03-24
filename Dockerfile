# syntax=docker/dockerfile:1
# ===========================================================================
# ERC-7730 Analyzer — production image
#
# Bakes the full analyzer + screenshot pipeline into a single image:
#   - Python 3.12 + all analyzer deps
#   - Node 20 + pnpm + device-sdk-ts (pre-built)
#   - Native Speculos + qemu-user-static (ARM emulation for Ledger apps)
#   - Runtime cache for Ethereum .elf app files fetched from app-ethereum CI
#
# Build:
#   docker build -t erc7730-analyzer .
#
# Run (service mode — default):
#   docker run --rm -p 8080:8080 --env-file .env erc7730-analyzer
#
# Run (CLI mode):
#   docker run --rm --env-file .env \
#     erc7730-analyzer cli --erc7730_file /data/descriptor.json
# ===========================================================================

# ======================== build args ========================
ARG DMK_REPO=LedgerHQ/device-sdk-ts
ARG DMK_REF=feat/no-issue-external-speculos
ARG CS_DEVICE=stax

# ---------- stage 1: build device-sdk-ts (public) ----------
FROM node:20-bookworm-slim AS dmk-builder

ARG DMK_REPO
ARG DMK_REF

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g pnpm@9

WORKDIR /build
RUN git clone --depth 1 --branch ${DMK_REF} \
        https://github.com/${DMK_REPO}.git . \
    && pnpm install --frozen-lockfile \
    && pnpm build:libs

RUN printf '{\n  "repo": "%s",\n  "ref": "%s"\n}\n' \
        "${DMK_REPO}" "${DMK_REF}" \
    > .erc7730_analyzer_dmk_ready.json

# ---------- final image ----------
FROM python:3.12-slim

ARG CS_DEVICE

# Node.js 20 runtime + pnpm (cs-tester execution)
COPY --from=dmk-builder /usr/local/ /usr/local/

# uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        qemu-user-static \
    && rm -rf /var/lib/apt/lists/*

# ---------- Python deps ----------
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# ---------- Native Speculos (no Docker-in-Docker needed) ----------
RUN pip install --no-cache-dir speculos

# ---------- Pre-built device-sdk-ts ----------
COPY --from=dmk-builder  /build  /data/screenshots/device-sdk-ts

# ---------- Runtime directories ----------
RUN mkdir -p /data/screenshots/ethereum-app-elfs

# ---------- Runtime config ----------
ENV PYTHONUNBUFFERED=1
ENV CS_TESTER_RUNTIME_ROOT=/data/screenshots
ENV CS_TESTER_ROOT=/data/screenshots/device-sdk-ts
ENV ETH_APP_ELF_ROOT=/data/screenshots/ethereum-app-elfs
ENV CS_TESTER_DEVICE=${CS_DEVICE}

EXPOSE 8080

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["service"]
