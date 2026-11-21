# Lustro ECR, bo Docker Hub ogranicza pobrania (429). Inne źródło: --build-arg PYTHON_IMAGE=python:3.12-slim
ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.12-slim
FROM ${PYTHON_IMAGE}
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
# OpenCV (zależność OCR) potrzebuje bibliotek systemowych, których nie ma w obrazie slim.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "scamdna.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
