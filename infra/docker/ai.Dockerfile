# Sabi AI service image. Built from the repository root:
#
#   docker build -f infra/docker/ai.Dockerfile -t <image> .
#
# The runtime command matches `make ai-serve`: uvicorn serves `app.main:app` from
# services/ai on port 8001.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/ai/ /srv/services/ai/
RUN pip install --no-cache-dir -e /srv/services/ai

WORKDIR /srv/services/ai

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
