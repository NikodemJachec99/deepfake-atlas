"""Ochrona API bez kont użytkowników (#186, docs/bezpieczenstwo.md).

1. Pochodzenie żądania: zapis (POST, PUT, PATCH, DELETE) pod /api/ z nagłówkiem `Origin` spoza
   `CORS_ALLOWED_ORIGINS` i spoza własnego hosta dostaje 403. Przeglądarka zawsze dołącza `Origin` do
   zapisu z innej strony, więc obca strona otwarta przez analityka nie zmieni werdyktu ani nie uruchomi
   analizy. Narzędzia bez przeglądarki (curl, skrypty) nie wysyłają `Origin` i przechodzą.
2. Opcjonalny klucz: gdy `API_WRITE_KEY` jest ustawiony, każdy zapis pod /api/ musi mieć ten klucz
   w `X-API-Key` albo `Authorization: Bearer`. Domyślnie wyłączony.
3. Limit rozmiaru: żądanie dłuższe niż `UPLOAD_MAX_BYTES` (z `Content-Length`) dostaje 413, zanim Django
   zacznie zapisywać pliki na dysk.
"""

import hmac
from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _origin(value: str) -> str:
    parts = urlsplit(value.strip())
    return f"{parts.scheme}://{parts.netloc}".lower() if parts.scheme and parts.netloc else value.strip().lower()


def _key_from(request) -> str:
    key = request.headers.get("X-API-Key", "")
    auth = request.headers.get("Authorization", "")
    if not key and auth.lower().startswith("bearer "):
        key = auth[7:]
    return key.strip()


class ApiGuardMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/") and request.method in UNSAFE:
            refused = self._check(request)
            if refused is not None:
                return refused
        return self.get_response(request)

    def _check(self, request):
        limit = int(getattr(settings, "UPLOAD_MAX_BYTES", 0) or 0)
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if limit and length > limit:
            return JsonResponse({"detail": f"Żądanie ma {length} bajtów, limit to {limit}."}, status=413)

        origin = request.headers.get("Origin")
        if origin:
            allowed = {_origin(o) for o in getattr(settings, "CORS_ALLOWED_ORIGINS", [])}
            own = _origin(f"{request.scheme}://{request.get_host()}")
            if _origin(origin) not in allowed | {own}:
                return JsonResponse({"detail": "Zapis z tej strony jest niedozwolony (Origin spoza listy)."}, status=403)

        expected = getattr(settings, "API_WRITE_KEY", "")
        if expected and not hmac.compare_digest(_key_from(request).encode(), expected.encode()):
            return JsonResponse({"detail": "Brak albo zły klucz API dla zapisu (X-API-Key)."}, status=401)
        return None
