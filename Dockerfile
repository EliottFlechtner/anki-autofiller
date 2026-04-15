FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

ARG PIP_INDEX_URL
ARG PIP_EXTRA_INDEX_URL
ARG PIP_RETRIES=1
ARG PIP_TIMEOUT=15

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --retries ${PIP_RETRIES} --timeout ${PIP_TIMEOUT} -r requirements.txt

COPY autofiller ./autofiller
COPY templates ./templates
COPY presets ./presets
COPY web_app.py ./web_app.py
COPY anki_autofiller.py ./anki_autofiller.py
COPY cli.py ./cli.py

RUN useradd --create-home --uid 10001 appuser
USER appuser

ENV ANKI_AUTOFILLER_FLASK_HOST=0.0.0.0 \
    ANKI_AUTOFILLER_FLASK_PORT=5000 \
    ANKI_AUTOFILLER_OUTPUT_PATH=/app/output/anki_import.tsv

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import sys, urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=3); sys.exit(0)"

CMD ["python", "web_app.py"]
