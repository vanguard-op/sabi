# Sabi API gateway image. Built from the repository root so the service root and
# its sibling packages are available:
#
#   docker build -f infra/docker/api.Dockerfile -t <image> .
#
# The runtime command is the same command the Makefile documents for a local boot
# (`make backend-serve`): uvicorn serves `app.main:app` from services/api.

FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Build tooling for wheels that need a compiler (psycopg binary wheel avoids it,
# but argon2-cffi and others may fall back).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install the service's pinned runtime dependencies from its own root.
COPY services/api/ /srv/services/api/
RUN pip install --no-cache-dir -e /srv/services/api

# The migrations tree lives at the repo root and is shared with the payment
# store; the API's alembic.ini resolves it relative to the service root.
COPY migrations/ /srv/migrations/

WORKDIR /srv/services/api

EXPOSE 8000

# Production boot command, identical to `make backend-serve`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
