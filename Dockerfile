FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

COPY --from=builder /install /usr/local
WORKDIR /app
COPY app ./app
COPY db ./db
COPY streamlit_app.py ./streamlit_app.py

RUN mkdir -p /app/data /app/reports && chown -R appuser:appuser /app

USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://localhost:{p}/health',timeout=3).status==200 else 1)"

# Shell form (not exec-array form) so $PORT expands -- unset locally/docker-compose
# (defaults to 8000, matching docker-compose.yml's port mapping), set by the platform
# on Render (which assigns its own port and expects the app to bind to it).
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
