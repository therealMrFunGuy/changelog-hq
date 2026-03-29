FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/changelog-hq

ENV PORT=8502
ENV CHANGELOG_DB_PATH=/data/changelog-hq/changelog.db
ENV LLM_URL=http://host.docker.internal:11435

EXPOSE 8502

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import httpx; httpx.get('http://localhost:8502/health').raise_for_status()" || exit 1

CMD ["python", "server.py"]
