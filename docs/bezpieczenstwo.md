# Bezpieczeństwo własnego API

Przegląd z 21.11.2026 ([#186](https://github.com/NikodemJachec99/deepfake-atlas/issues/186)). API nie ma kont użytkowników: działa w sieci lokalnej zespołu analityków, przyjmuje adresy i pliki od użytkownika i pobiera strony oszustów. Poniżej, co sprawdziliśmy, co poprawiliśmy i jakie ryzyko zostaje. Testy: `backend/tests/test_security.py`.

## Poprawione

| Ryzyko | Co było | Co jest teraz |
|---|---|---|
| Zapis z obcej strony (CSRF) | Obca strona otwarta w przeglądarce analityka mogła wysłać formularz POST, który zmienia werdykt krawędzi albo uruchamia analizę dowolnego adresu: API przyjmowało formularze i nie sprawdzało pochodzenia | zapis pod `/api/` z nagłówkiem `Origin` spoza `CORS_ALLOWED_ORIGINS` i spoza własnego hosta dostaje 403 (`api/security.py`); API przyjmuje tylko JSON, a upload plików ma jawny parser i to samo sprawdzenie pochodzenia |
| Brak kontroli zapisu | każdy w sieci mógł zapisywać | opcjonalny klucz `API_WRITE_KEY`: gdy ustawiony, zapis wymaga `X-API-Key` albo `Authorization: Bearer`; frontend wysyła `NEXT_PUBLIC_API_KEY`; domyślnie wyłączony |
| Rozmiar uploadu | limit był tylko na rozpakowane archiwum (2 GiB, 5000 plików), samo żądanie mogło być dowolnie duże | żądanie dłuższe niż `UPLOAD_MAX_BYTES` (domyślnie 2 GiB plus 64 MiB) dostaje 413, zanim pliki trafią na dysk |
| Nazwy plików w uploadzie | nazwa `..`, `.` albo pusta kończyła się błędem 500 | 400 z opisem; nazwy zaczynające się od kropki też są odrzucane |
| SSRF przy odcisku certyfikatu | wzbogacanie łączyło się z hostem strony bez sprawdzenia adresu, więc podmiana DNS między pobraniem strony a wzbogacaniem mogła skierować połączenie do sieci wewnętrznej | odcisk TLS łączy się tylko z adresem publicznym, sprawdzonym tak jak w crawlerze (`resolve_public`), z nazwą w SNI |
| Nadużycie analiz | bez limitu liczby nowych analiz | 60 na minutę na klienta (`ANALYSES_RATE`), dla `POST /api/analyses` i uploadu |
| Osadzanie w ramce | odpowiedzi bez `X-Frame-Options` | `X-Frame-Options: DENY` dla wszystkich odpowiedzi |
| Tryb debugowania | `.env.example` miał `DJANGO_DEBUG=1`, więc błąd 500 pokazywał w sieci ślad stosu i ustawienia | `.env.example` ma `DJANGO_DEBUG=0`; istniejące stosy trzeba zmienić we własnym `.env` |

## Sprawdzone, bez zmian

| Obszar | Stan |
|---|---|
| Zip slip | każda ścieżka w archiwum jest sprawdzana przed rozpakowaniem; wyjście poza katalog daje 400 |
| Bomba ZIP | suma rozmiarów z nagłówków ponad 2 GiB albo ponad 5000 plików daje 400; `zipfile` nie wypakuje więcej, niż deklaruje nagłówek (niezgodność daje błąd CRC); dowiązań symbolicznych `zipfile` nie tworzy |
| SSRF crawlera | od #162 każdy skok przekierowania przechodzi przez `resolve_public` (odmowa, gdy którykolwiek adres z DNS jest niepubliczny), a połączenie idzie na przypięty, sprawdzony adres; favicona idzie tą samą drogą |
| Renderowanie treści oszustów | `/api/artifacts/{sha}` zawsze jako załącznik, HTML i HAR jako `text/plain`, `nosniff`, `Content-Security-Policy: sandbox; default-src 'none'`; `/image` tylko dla obrazów po sygnaturze bajtów (bez SVG), `/video` tylko dla MP4, MOV i WebM po sygnaturze; frontend pokazuje tekst, nie HTML stron |
| Tokeny w adresach | `redact_url` zamienia tokeny na skróty przy zgłoszeniu adresu, w markerach, w eksporcie i w notatkach decyzji (pamięć sprzeciwu); token Mety jest rozpoznawany pod dowolną nazwą parametru |
| CORS | tylko adresy z `CORS_ALLOWED_ORIGINS`; bez ciasteczek uwierzytelniających |
| Zapytania do bazy | wyłącznie ORM Django, bez surowego SQL z danych użytkownika |
| Usługi zewnętrzne | Jev domyślnie wyłączony, bez zgody nie wysyła danych spraw (docs/jev.md); crt.sh i RDAP dostają tylko nazwę domeny |

## Ryzyko, które zostaje

- **Odczyt jest otwarty.** Każdy, kto ma dostęp do portu API, czyta korpus, dowody, notatki analityków i pobiera eksport (`/api/export`). To dane organizatora, więc API ma działać tylko w sieci zespołu, za zaporą albo VPN. Klucz zapisu nie chroni odczytu.
- **Klucz we frontendzie nie jest tajny.** `NEXT_PUBLIC_API_KEY` trafia do kodu strony. Chroni przed zapisem z obcych stron i skryptów w sieci, ale nie przed kimś, kto ma dostęp do interfejsu. Prawdziwe konta i role to dalszy etap.
- **Tekst zgłoszony jako treść reklamy** (`kind=text`) zapisujemy dosłownie. Token wklejony w zwykły tekst, a nie w adres, nie zostanie zamieniony na skrót.
- **Panel administracyjny Django** (`/admin/`) jest pod tym samym portem. Bez założonego konta nie da się do niego wejść, ale nie zakładamy kont na wspólnych stosach.
- **Limit analiz** liczy się w pamięci procesu, więc przy kilku procesach backendu każdy ma własny licznik.

## Ustawienia

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `API_WRITE_KEY` | pusta | klucz zapisu przez API; pusty: wyłączony |
| `NEXT_PUBLIC_API_KEY` | pusta | ten sam klucz dla frontendu, wkompilowany przy budowaniu |
| `UPLOAD_MAX_BYTES` | 2214592512 | największe żądanie w bajtach |
| `ANALYSES_RATE` | `60/min` | limit nowych analiz na klienta |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | skąd wolno czytać i zapisywać z przeglądarki; przy innym porcie frontendu dopisz jego adres |
| `DJANGO_DEBUG` | `0` w `.env.example` | `1` tylko do pracy lokalnej |
