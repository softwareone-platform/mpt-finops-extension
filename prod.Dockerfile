FROM python:3.12.2-slim-bookworm

# Install curl and certificates for uv installer
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Install uv
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh

ENV PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy \
    PATH="/extension/.venv/bin:/root/.local/bin:$PATH"

WORKDIR /extension

COPY pyproject.toml uv.lock ./

# Install all dependencies (including dev tools for testing)
# Removed BuildKit cache mount
RUN uv sync --frozen --all-groups --no-install-project

COPY . .

# Re-run sync to install project itself
# Removed BuildKit cache mount
RUN uv sync --frozen --all-groups

CMD ["swoext", "run", "--no-color"]
