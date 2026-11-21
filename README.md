# SCAM DNA (Deepfake Atlas): Kolekcjoner Fejków, HackNation 2026

System łączy pozornie niezależne fałszywe reklamy w kampanie i operatorów na podstawie wspólnych śladów cyfrowych. Do każdego połączenia podaje dowody. Zadanie NASK "Follow the Fake".

- **Metodyka** (cechy, podobieństwo, grupowanie): [docs/metodyka.md](docs/metodyka.md)
- Wymagania zadania i zgodność z regulaminem: [docs/wymagania.md](docs/wymagania.md)
- Teksty zgłoszenia na HackTribe: [docs/zgloszenie.md](docs/zgloszenie.md)
- Wyniki na danych organizatora: [docs/dane-organizatora.md](docs/dane-organizatora.md)
- Kontrakt API: [docs/api.md](docs/api.md)
- Laboratorium dowodów (co zostaje z połączenia po wyłączeniu śladów): [docs/laboratorium.md](docs/laboratorium.md)
- Dwie strony pod jednym adresem w sprawie 61, audyt przechwyceń: [docs/dwie-twarze.md](docs/dwie-twarze.md)
- Prompt do designu interfejsu: [docs/design-prompt.md](docs/design-prompt.md)
- Biblioteki, modele, usługi, dane i ich licencje: [docs/licencje.md](docs/licencje.md)
- Plan rozwoju na rok: [docs/plan-roczny.md](docs/plan-roczny.md)

## Start

```bash
cp .env.example .env
docker compose up -d --build
curl localhost:8000/health                                           # {"status": "ok"}

docker compose exec backend python manage.py seed_people            # baza referencyjna osób
docker compose exec backend python manage.py collect cert_pl        # Lista Ostrzeżeń CERT Polska, ok. 127 tys. domen
docker compose exec backend python manage.py import_bundle /data/raw/nask --name nask   # paczka organizatora

```

Interfejs: http://localhost:3000 (kontener `frontend`).

Wymagania: Docker z Compose, ok. 6 GB RAM na wszystkie usługi, ok. 8 GB miejsca na obrazy, dostęp do internetu przy pierwszym budowaniu obrazów i przy pierwszym użyciu OCR (pobranie modelu). Pierwsze `up --build` pobiera obrazy usług i paczki Pythona (m.in. onnxruntime, OpenCV, numpy). Sprawdzone 2026-11-21 na świeżym klonie z pustymi wolumenami: na Windowsie przy łączu ok. 100 KB/s `up --build` trwało 31 minut, import paczki `nask` (13 stron) 58 sekund; na Linuksie (Ubuntu 24.04 w WSL2, klon w systemie plików Linuksa, bash) 16 minut i 161 sekund, z tym samym wynikiem. Na macOS nie sprawdzaliśmy. CI przy każdym PR stawia cały stos na ubuntu i importuje zmyśloną sprawę (`backend/tests/smoke_compose.py`).

Porty zmienisz w `.env`: `BACKEND_PORT`, `FRONTEND_PORT`, a jeśli masz zajęte porty usług pomocniczych (np. własny Postgres na 5432), także `DB_PORT`, `REDIS_PORT`, `TEMPORAL_PORT`, `S3_PORT`, `NEO4J_HTTP_PORT`, `OPENSEARCH_PORT` i pozostałe z `.env.example`. Po zmianie `FRONTEND_PORT` dopisz nowy adres interfejsu do `CORS_ALLOWED_ORIGINS`, a po zmianie `BACKEND_PORT` przebuduj interfejs (`docker compose up -d --build frontend`), bo adres API jest wkompilowany w czasie budowania.

Windows z Git Bash: przed poleceniami z `/data/...` ustaw `export MSYS_NO_PATHCONV=1`, inaczej Git Bash zamieni ścieżkę kontenera na ścieżkę Windows i `import_bundle` nie znajdzie katalogu. W PowerShellu i cmd ten problem nie występuje. Praca nad interfejsem bez kontenera:

```bash
cd frontend && cp .env.local.example .env.local && npm install && npm run dev
```

Paczkę organizatora rozpakuj do `data/raw/nask/` (katalog jest poza gitem). Polecenie `import_bundle` importuje sprawy, analizuje je i wypisuje raport powiązań.

Analiza z konsoli:

```bash
curl -X POST localhost:8000/api/analyses -H "Content-Type: application/json" -d '{"kind":"url","value":"https://przyklad.example/"}'
curl -X POST localhost:8000/api/analyses/upload -F "files=@sprawa.zip"
curl -N localhost:8000/api/analyses/<id>/events
```

## Jak to działa

1. **Wejście.** Adres URL, tekst, zrzut ekranu reklamy, zapisana strona, plik HAR albo ZIP z całą sprawą. Do tego konektory bibliotek reklam (`collectors/`).
2. **Potok analizy** (`workflows/pipeline.py`), sześć etapów: przyjęcie, strona i łańcuch przekierowań, ekstrakcja markerów, wzbogacanie infrastruktury, szukanie powiązań, przypisanie do kampanii i operatora. Każdy etap zapisuje wynik do bazy, więc Temporal może go ponowić osobno. Materiał z przechwycenia analizujemy bez sieci.
3. **Genom reklamy.** Markery w 7 rodzinach: infrastruktura, tracking i lejek, szablon strony, kreacja, narracja, osoby i marki, zachowanie. Rejestr typów z siłą dowodową: `evidence/kinds.py`.
4. **Evidence Fusion** (`similarity/fusion.py`). Model Fellegi-Sunter z ważeniem rzadkością. Wspólny adres z puli Cloudflare jest wart prawie zero, wspólny identyfikator strony w panelu lejka rozstrzyga. Rzadkość liczona po niezależnych źródłach, nie po reklamach.
5. **Krawędź z dowodami.** Tabele `Edge` i `EdgeEvidence` w Postgresie. Krawędź bez dowodów nie powstaje.
6. **Trzy relacje.** `same_campaign` (to samo źródło i ta sama opowieść), `same_operator` (to samo zaplecze, inna opowieść), `similar` (podobna koncepcja bez dowodu wspólnego zaplecza). Duplikaty są oznaczane osobno.
7. **Ocena nowego materiału.** Duplikat, nowa odsłona znanej kampanii, nowa kampania znanego operatora, tylko podobna koncepcja albo nowy wzorzec.
8. **Kampanie i operatorzy.** Nowa reklama dołącza do istniejącej kampanii i operatora. Analityk może odrzucić krawędź i wtedy przestaje ona cokolwiek spinać.

## Skąd biorą się ślady

| Materiał | Co z niego wyciągamy |
|---|---|
| Adres URL | domena, szablon ścieżki, zestaw parametrów, piksele i klucze afiliacyjne przemycane w parametrach, identyfikatory reklam Meta, nazewnictwo zestawów reklam, cyrylica w wartościach |
| HAR | łańcuch przekierowań, ścieżki zaplecza strony (odcisk silnika lejka), hosty zasobów i trackerów, identyfikatory z żądań POST, adres IP z chwili przechwycenia, sygnatura serwera |
| HTML | identyfikatory śledzące, kontakty, formularze, tytuł, treść (MinHash), struktura DOM, podszycie pod markę, wzmianki o osobach, słowa kluczowe, tematyka |
| Zrzut ekranu reklamy | OCR: nazwa reklamodawcy, tekst reklamy, numer z Biblioteki Reklam Mety; hash percepcyjny kreacji |
| Obrazy strony (z HAR i z katalogu `_files`) | zbiór haszy percepcyjnych: te same zdjęcia na różnych domenach |
| Archiwum NASK | adres IP i numer seryjny certyfikatu z `dns_ssl.json` |
| Strona na żywo | DNS, ASN, certyfikat TLS, favicon, RDAP, różnica między stroną dla bota i dla ofiary |
| Lista Ostrzeżeń CERT Polska | etykieta: czy domena jest na liście i od kiedy |

Tokeny dostępu znalezione w adresach (np. `access_token`) zapisujemy wyłącznie jako skrót.

## Stack

| Warstwa | Technologia |
|---|---|
| API | Django 5.2 + DRF + OpenAPI, ASGI (uvicorn) |
| Orkiestracja | Temporal + worker Python (`workflows/`) |
| Źródło prawdy | PostgreSQL 16 + pgvector |
| Dowody | magazyn S3 (RustFS), obiekty adresowane hashem treści |
| Projekcje | Neo4j (`manage.py project_graph`), OpenSearch (`manage.py index_ads`) |
| OCR i obrazy | RapidOCR z modelami PP-OCRv5 (lokalnie, ONNX), hash percepcyjny dHash (Pillow) |
| Frontend | Next.js 16 + React 19 + TypeScript + Tailwind 4 |

Usługi w compose: `db` 5432, `redis` 6380, `temporal` 7233 (UI 8233), `s3` 9000 (konsola 9001), `neo4j` 7474/7687, `opensearch` 9200, `backend` 8000, `worker`.

## Polecenia

```bash
python manage.py import_bundle <katalog> --name <nazwa>  # paczka przechwyceń: import, analiza, raport
python manage.py fill_certs                             # dociąga crt.sh dla domen, które przy imporcie zostały bez odpowiedzi
python manage.py seed_people                            # baza referencyjna osób
python manage.py collect cert_pl                        # bieżąca lista ostrzeżeń
python manage.py collect cert_pl_history --year 2025    # historia z actions_YYYY.log
python manage.py collect microsoft --query <fraza>      # Microsoft Ad Library, bez klucza
python manage.py collect meta --query <fraza>           # wymaga META_AD_LIBRARY_TOKEN
python manage.py ensure_schedules                       # harmonogramy skanów w Temporalu
python manage.py ensure_schedules --pause               # wstrzymuje skany bibliotek reklam (np. na demo), --resume wznawia
python manage.py project_graph                          # odbudowa grafu w Neo4j
python manage.py index_ads                              # odbudowa indeksu w OpenSearch
python manage.py reset_corpus --yes                     # czyści korpus, zostawia listę CERT i osoby
python manage.py export_corpus <katalog>                # wzbogacony korpus do plików: reklamy z markerami, krawędzie z dowodami, grupy
```

## Testy

```bash
cd backend
uv venv --python 3.12 .venv && uv pip install --python .venv -r requirements.txt
docker compose up -d db
.venv/Scripts/python -m pytest -q     # Linux/macOS: .venv/bin/python
.venv/Scripts/ruff check .            # Linux/macOS: .venv/bin/ruff
```

Bez `uv` (np. czyste Ubuntu): `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`. W Ubuntu potrzebny jest pakiet `python3-venv`. Testy łączą się z Postgresem na `localhost:5432`; przy innym `DB_PORT` ustaw `DATABASE_URL`.

Testy potoku i API działają na prawdziwym Postgresie z pgvector. Sieć zastępują podstawki z `tests/fakes.py`. Dane w testach są zmyślone, formaty pochodzą z prawdziwych przechwyceń.

## Stan

Sprawdzone 2026-11-21:
- Paczka organizatora (10 spraw, 13 stron) i paczka z zagadki (15 spraw): wyniki w [docs/dane-organizatora.md](docs/dane-organizatora.md).
- Lista CERT Polska: 126 642 domeny wczytane w 13 s.
- Microsoft Ad Library: 20 reklam z Polski przeszło cały potok na żywo.
- Analiza zlecona przez API wykonana przez Temporal, postęp odebrany przez SSE, dowody w S3.
- Projekcja do Neo4j, indeks w OpenSearch, skan z harmonogramu Temporala.

Jeszcze nie ma:
- Rozpoznawania głosu i ruchu. Z nagrań reklam bierzemy 8 klatek (hasze, tekst z OCR, twarze) i mowę zamienioną na tekst lokalnym modelem Whisper (pierwsze 120 s, `TRANSCRIBE=off` wyłącza, `python manage.py transcribe_videos` przelicza już zaimportowane nagrania). Porównania mówcy i klonu głosu nie ma. Twarze rozpoznajemy tylko dla osób z małej bazy referencyjnej (`python manage.py build_face_refs` ją odbudowuje, modele pobierają się przy pierwszym użyciu). Obrazy porównujemy hashem percepcyjnym, reklamodawcę i tekst ze zrzutu czyta OCR.
- Crawler z przeglądarką (Chromium w osobnym kontenerze, [docs/crawler.md](docs/crawler.md)) nie ma jeszcze wyjścia przez polski adres domowy ani zachowania ludzkiego. Strony z wykrywaniem automatu po odcisku przeglądarki mogą pokazać białą stronę.
- Konektor Mety jest napisany według dokumentacji, nie był uruchomiony na żywym tokenie.
- Wagi uczone metodą EM (`python manage.py estimate_weights`, `MODEL_WEIGHTS=learned`) są policzone, ale domyślnie działają eksperckie: na 28 reklamach z paczek uczone dają to samo grupowanie, a na korpusie z reklamami Microsoft łamią rdzeń operatora A. Kalibracji na decyzjach analityka nie ma, bo decyzji jest 0. Wyniki w [docs/dane-organizatora.md](docs/dane-organizatora.md).
- Logo marki na obrazie nie rozpoznajemy: CLIP zero-shot na całym zrzucie dawał przewagę najwyżej 0,027 nad drugą marką. Podobne ujęcie (ten sam kadr w innej wersji) rozpoznajemy.
- API nie ma uwierzytelniania. Do pracy lokalnej i demo, nie do wystawienia w sieci.

## Zasady pracy

1. `main` zawsze działa. Zmiany przez PR.
2. Gałęzie `feat/<co>`, `fix/<co>`. Małe PR-y.
3. Zmiana API zaczyna się od `docs/api.md` i `frontend/src/lib/api.ts`.
4. Sekrety tylko w `.env`. Dane organizatora tylko w `data/raw/`, nigdy w gicie.
