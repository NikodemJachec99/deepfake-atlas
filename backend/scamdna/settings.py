"""Konfiguracja SCAM DNA. Wszystko, co zależy od środowiska, pochodzi ze zmiennych środowiskowych."""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = env("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "ads",
    "evidence",
    "similarity",
    "enrichment",
    "people",
    "collectors",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "scamdna.urls"
ASGI_APPLICATION = "scamdna.asgi.application"
WSGI_APPLICATION = "scamdna.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "postgres://hack:hack@localhost:5432/deepfake_atlas"), conn_max_age=60
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "pl"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

CORS_ALLOWED_ORIGINS = [o for o in env("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o]

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    # Na start API jest otwarte w sieci lokalnej. Role i klucze instytucji wchodzą w M10 do M12.
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}
SPECTACULAR_SETTINGS = {
    "TITLE": "SCAM DNA API",
    "DESCRIPTION": "Łączenie fałszywych reklam w kampanie na podstawie wspólnych śladów.",
    "VERSION": "0.1.0",
}

# --- Analiza ---------------------------------------------------------------
# temporal: produkcyjnie, trwały workflow. thread: lokalnie bez Temporala. sync: testy.
ANALYSIS_RUNNER = env("ANALYSIS_RUNNER", "thread")
TEMPORAL_ADDRESS = env("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = env("TEMPORAL_NAMESPACE", "default")
TEMPORAL_TASK_QUEUE = env("TEMPORAL_TASK_QUEUE", "scamdna")

CRAWLER_FETCHER = env("CRAWLER_FETCHER", "crawler.fetch.HttpFetcher")
ENRICHER = env("ENRICHER", "enrichment.providers.LiveEnricher")

# Opcjonalny lokalny model decyzji basal (docs/basal.md). Pusty adres albo tryb "off" wyłącza go całkowicie.
BASAL_URL = env("BASAL_URL", "")
BASAL_MODE = env("BASAL_MODE", "off")  # off | shadow | on
BASAL_MODEL = env("BASAL_MODEL", "")
BASAL_REVISION = env("BASAL_REVISION", "")
BASAL_VARIANT = env("BASAL_VARIANT", "")
BASAL_API_KEY = env("BASAL_API_KEY", "")
BASAL_TIMEOUT = float(env("BASAL_TIMEOUT", "20"))
BASAL_MAX_ERROR = env("BASAL_MAX_ERROR", "")  # np. 0.05; pusty: bez wstrzymywania
# Poza tymi hostami adapter nie wyśle niczego. Model ma działać lokalnie.
BASAL_ALLOWED_HOSTS = [h for h in env("BASAL_ALLOWED_HOSTS", "127.0.0.1,localhost,::1,basal,host.docker.internal").split(",") if h]
CRAWLER_TIMEOUT = float(env("CRAWLER_TIMEOUT", "15"))
CRAWLER_MAX_HOPS = int(env("CRAWLER_MAX_HOPS", "10"))
CRAWLER_MAX_BYTES = int(env("CRAWLER_MAX_BYTES", str(3 * 1024 * 1024)))
# Wyjście crawlera. Oszuści blokują adresy centrów danych, docelowo polski adres domowy lub mobilny.
CRAWLER_PROXY = env("CRAWLER_PROXY")

# --- Magazyn dowodów -------------------------------------------------------
ARTIFACT_BACKEND = env("ARTIFACT_BACKEND", "local")  # local | s3
ARTIFACT_DIR = Path(env("ARTIFACT_DIR", str(BASE_DIR.parent / "data" / "artifacts")))

# Modele pobierane przy pierwszym użyciu (twarze: YuNet i SFace). Katalog poza gitem.
MODELS_DIR = Path(env("MODELS_DIR", str(BASE_DIR.parent / "data" / "models")))
FACE_MODELS_DOWNLOAD = env("FACE_MODELS_DOWNLOAD", "1") == "1"
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", "http://localhost:9000")
S3_ACCESS_KEY = env("S3_ACCESS_KEY", "scamdna")
S3_SECRET_KEY = env("S3_SECRET_KEY", "scamdna-secret")
S3_BUCKET = env("S3_BUCKET", "evidence")

# --- Projekcje -------------------------------------------------------------
NEO4J_URI = env("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = env("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = env("NEO4J_PASSWORD", "scamdna-neo4j")
OPENSEARCH_URL = env("OPENSEARCH_URL", "http://localhost:9200")
OPENSEARCH_INDEX = env("OPENSEARCH_INDEX", "ads")

# --- Źródła danych ---------------------------------------------------------
META_AD_LIBRARY_TOKEN = env("META_AD_LIBRARY_TOKEN")
META_GRAPH_VERSION = env("META_GRAPH_VERSION", "v23.0")
TEXT_EMBEDDING_DIM = 1024
