# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy project metadata + lock files
COPY pyproject.toml uv.lock README.md ./
COPY package.json package-lock.json ./

# Copy source (includes service/ and utils/)
COPY src/ ./src/

# Copy helper scripts (mock OIDC, test harness)
COPY scripts/ ./scripts/

# Install Python dependencies (no dev deps in production image)
RUN uv sync --frozen --no-dev

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose the service port
EXPOSE 8730

# Default: run the analyzer CLI
# Override with: docker run <image> python -m service.app  (for service mode)
ENTRYPOINT ["uv", "run"]
CMD ["analyze_7730", "--help"]
