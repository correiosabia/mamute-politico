FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=UTC

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron bash \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copia o pacote em /app/mamute_scrappers para que os imports absolutos
# (from mamute_scrappers.db ...) e os jobs `python -m mamute_scrappers.*` resolvam.
COPY . /app/mamute_scrappers

RUN chmod +x \
    /app/mamute_scrappers/docker/entrypoint.sh \
    /app/mamute_scrappers/docker/run-cron-job.sh

ENTRYPOINT ["/app/mamute_scrappers/docker/entrypoint.sh"]
