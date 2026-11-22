"""Błędy API zawsze jako JSON `{"detail": "..."}`, bez strony debug Django i bez tracebacku."""

import asyncio
import logging
import re

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.conf import settings
from django.db import InterfaceError, OperationalError
from django.http import Http404, JsonResponse
from django.views.defaults import server_error as html_server_error
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

log = logging.getLogger(__name__)

ID_MAX = 2**62


class BadParameter(APIException):
    """Zły parametr zapytania: 400 z komunikatem po polsku."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_parameter"


def int_param(params, name: str, default: int | None = None, minimum: int | None = None, maximum: int | None = None) -> int | None:
    """Liczba całkowita z parametru zapytania. Brak albo pusty parametr daje `default`, zła wartość `BadParameter`."""
    raw = params.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise BadParameter(f"Parametr {name} musi być liczbą całkowitą") from None
    if minimum is not None and value < minimum:
        raise BadParameter(f"Parametr {name} nie może być mniejszy niż {minimum}")
    if maximum is not None and value > maximum:
        raise BadParameter(f"Parametr {name} nie może być większy niż {maximum}")
    return value


def id_param(params, name: str) -> int | None:
    return int_param(params, name, minimum=1, maximum=ID_MAX)


# get_object_or_404 Django pisze po angielsku "No Campaign matches the given query.", bez tłumaczenia.
_MISSING = re.compile(r"^No (\w+) matches the given query\.?$")
_MISSING_NAMES = {
    "Ad": "reklamy",
    "Alert": "alertu",
    "Analysis": "analizy",
    "Artifact": "artefaktu",
    "Campaign": "kampanii",
    "Edge": "krawędzi",
    "HuntCandidate": "kandydata łowcy",
    "HuntRun": "przebiegu łowcy",
    "Operator": "operatora",
    "Premise": "przesłanki",
}


def not_found_detail(message: str) -> str:
    """Komunikat 404 po polsku. Własne polskie komunikaty zostają bez zmian."""
    match = _MISSING.match(message or "")
    if match:
        return f"Nie ma {_MISSING_NAMES.get(match.group(1), 'takiego obiektu')} o tym identyfikatorze."
    if not message or message.startswith(("No ", "Not found")):
        return "Nie znaleziono."
    return message


def handler(exc, context):
    """Handler DRF. Nieobsłużony wyjątek to JSON 500 (przeciążona baza: 503). Przy DEBUG=1 zostaje strona debug."""
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, Http404):
        response.data = {"detail": not_found_detail(str(exc))}
    if response is not None or settings.DEBUG:
        return response
    log.exception("Nieobsłużony błąd w %s", context.get("view").__class__.__name__, exc_info=exc)
    if isinstance(exc, (OperationalError, InterfaceError)):
        return Response({"detail": "Baza danych jest chwilowo przeciążona. Spróbuj ponownie za chwilę."}, status=503)
    return Response({"detail": "Błąd serwera."}, status=500)


def not_found(request, exception=None, *args, **kwargs):
    """`handler404` dla widoków spoza DRF (np. obrazy artefaktów): JSON po polsku dla ścieżek /api/."""
    if request.path.startswith("/api/"):
        return JsonResponse({"detail": not_found_detail(str(exception) if exception else "")}, status=404)
    from django.views.defaults import page_not_found

    return page_not_found(request, exception)


def server_error(request, *args, **kwargs):
    """`handler500` dla widoków spoza DRF: JSON dla ścieżek /api/, reszta jak domyślnie."""
    if request.path.startswith("/api/"):
        return JsonResponse({"detail": "Błąd serwera."}, status=500)
    return html_server_error(request, *args, **kwargs)


class ConcurrencyLimitMiddleware:
    """Ogranicza liczbę żądań wykonywanych naraz. Każde żądanie API otwiera własne połączenie z bazą,
    a Postgres ma ich 100 (łącznie z workerem i analizami w tle). Nadmiar czeka w kolejce zamiast
    kończyć się błędem "too many clients". Strumienie SSE zwalniają miejsce, gdy zwrócą odpowiedź."""

    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.limit = int(getattr(settings, "API_MAX_CONCURRENCY", 24))
        self._semaphores: dict[int, asyncio.Semaphore] = {}
        if iscoroutinefunction(get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        if iscoroutinefunction(self):
            return self._limited(request)
        return self.get_response(request)  # tryb synchroniczny (WSGI, testy): bez limitu

    async def _limited(self, request):
        loop = asyncio.get_running_loop()
        semaphore = self._semaphores.setdefault(id(loop), asyncio.Semaphore(self.limit))
        async with semaphore:
            return await self.get_response(request)
