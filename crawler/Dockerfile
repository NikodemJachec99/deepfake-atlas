# Lustro ECR, bo Docker Hub ogranicza pobrania (429). Inne źródło: --build-arg PYTHON_IMAGE=python:3.12-slim
ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.12-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Playwright (Apache-2.0) i Chromium z zależnościami systemowymi. libatomic1 potrzebuje node z pakietu Playwright.
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && pip install --no-cache-dir --root-user-action=ignore playwright==1.65.2 \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 render
WORKDIR /app
COPY server.py check_guard.py ./
USER render

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["python", "server.py"]
