# Sabi isolated payment module image. Built from the repository root:
#
#   docker build -f infra/docker/payments.Dockerfile -t <image> .
#
# The module keeps its own schema, transaction boundary, and audit log
# (architecture.md, "Payment Module"); its package root is services/payments.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY services/payments/ /srv/services/payments/
RUN pip install --no-cache-dir -e /srv/services/payments

# The payments migrations tree, resolved relative to the service root.
COPY migrations/ /srv/migrations/

WORKDIR /srv/services/payments

EXPOSE 8002

CMD ["uvicorn", "sabi_payments.main:app", "--host", "0.0.0.0", "--port", "8002"]
