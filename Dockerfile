# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy project metadata + source needed for package build
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install dependencies and the project package
RUN uv sync --frozen --no-dev

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Entry point
ENTRYPOINT ["uv", "run", "analyze_7730"]
CMD ["--help"]
