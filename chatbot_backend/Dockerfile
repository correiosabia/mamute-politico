FROM python:3.11-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=UTC

WORKDIR /app

# cron roda a sincronização incremental do índice vetorial ao lado da API.
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore -r /app/requirements.txt

# O pacote vai para /app/chatbot_backend (e não /app/app) para que os imports
# absolutos `chatbot_backend.app...` usados pelos scripts resolvam. Antes só
# `app/` era copiado, então `chatbot_backend.scripts.*` sequer existia dentro da
# imagem — não havia como rodar ingestão nem sincronização em produção.
COPY . /app/chatbot_backend

RUN chmod +x /app/chatbot_backend/docker/entrypoint.sh

ENTRYPOINT ["/app/chatbot_backend/docker/entrypoint.sh"]
