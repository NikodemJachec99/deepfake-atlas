# SCAM DNA (Deepfake Atlas): Kolekcjoner Fejków, HackNation 2026

System łączy pozornie niezależne fałszywe reklamy w kampanie na podstawie wspólnych śladów cyfrowych i do każdego połączenia podaje dowody. Zadanie NASK "Follow the Fake".

- Wymagania zadania: [docs/wymagania.md](docs/wymagania.md)
- Kontrakt API: [docs/api.md](docs/api.md)
- Prompt do designu interfejsu: [docs/design-prompt.md](docs/design-prompt.md)
- Zależności i licencje: [docs/licencje.md](docs/licencje.md)
- Plan roczny, pełny inwentarz danych i modeli: https://claude.ai/artifact/LJNbSpF3byJLrYPdA8haFt

## Start

```bash
cp .env.example .env
docker compose up -d --build
curl localhost:8000/health                                   # {"status":"ok"}
docker compose exec backend python manage.py collect cert_pl # Lista Ostrzeżeń CERT Polska, ok. 127 tys. domen
docker compose exec backend python manage.py collect microsoft --query inwestycje --limit 20

cd frontend && cp .env.local.example .env.local && npm install && npm run dev   # http://localhost:3000
```

Analiza z konsoli:

```bash
curl -X POST localhost:8000/api/analyses -H "Content-Type: application/json" -d '{"kind":"url","value":"https://przyklad.example/"}'
curl -N localhost:8000/api/analyses/<id>/events
```

## Jak to działa

1. **Kolekcja.** Konektory bibliotek reklam (`collectors/`) i zgłoszenia ręczne. Każdy skan zostawia migawkę reklamy.
2. **Potok analizy** (`workflows/pipeline.py`), sześć etapów: przyjęcie, pobranie strony w dwóch profilach (bot i ofiara), ekstrakcja markerów, wzbogacanie infrastruktury, szukanie powiązań, przypisanie do kampanii. Każdy etap zapisuje wynik do bazy, więc Temporal może go ponowić osobno.
3. **Genom reklamy.** Markery w 7 rodzinach: infrastruktura, tracking i lejek, szablon strony, kreacja, narracja, osoby i marki, zachowanie. Rejestr typów z siłą dowodową: `evidence/kinds.py`.
4. **Evidence Fusion** (`similarity/fusion.py`). Model Fellegi-Sunter z ważeniem rzadkością. Wspólny ASN dużego dostawcy jest wart prawie zero, wspólny identyfikator analityki rozstrzyga. Rzadkość liczona po niezależnych źródłach, nie po reklamach.
5. **Krawędź z dowodami.** Tabele `Edge` i `EdgeEvidence` w Postgresie. Krawędź bez dowodów nie powstaje.
6. **Kampanie.** Składowe spójne po krawędziach `same_campaign`, których analityk nie odrzucił. Nowa reklama dołącza do istniejącej kampanii.

## Stack

| Warstwa | Technologia |
|---|---|
| API | Django 5.2 + DRF + OpenAPI, ASGI (uvicorn) |
| Orkiestracja | Temporal + worker Python (`workflows/`) |
| Źródło prawdy | PostgreSQL 16 + pgvector |
| Dowody | magazyn S3 (RustFS), obiekty adresowane hashem treści |
| Projekcje | Neo4j (`manage.py project_graph`), OpenSearch (`manage.py index_ads`) |
| Frontend | Next.js 16 + React 19 + TypeScript + Tailwind 4 |

Usługi w compose: `db` 5432, `redis` 6380, `temporal` 7233 (UI 8233), `s3` 9000 (konsola 9001), `neo4j` 7474/7687, `opensearch` 9200, `backend` 8000, `worker`.

## Polecenia

```bash
python manage.py collect cert_pl                      # bieżąca lista ostrzeżeń
python manage.py collect cert_pl_history --year 2025  # historia z actions_YYYY.log
python manage.py collect microsoft --query <fraza>    # Microsoft Ad Library, bez klucza
python manage.py collect meta --query <fraza>         # wymaga META_AD_LIBRARY_TOKEN
python manage.py ensure_schedules                     # harmonogramy skanów w Temporalu
python manage.py project_graph                        # odbudowa grafu w Neo4j
python manage.py index_ads                            # odbudowa indeksu w OpenSearch
```

## Testy

```bash
cd backend
uv venv --python 3.12 .venv && uv pip install --python .venv -r requirements.txt
docker compose up -d db
.venv/Scripts/python -m pytest -q     # Linux/macOS: .venv/bin/python
.venv/Scripts/ruff check .
```

Testy potoku i API działają na prawdziwym Postgresie z pgvector. Sieć zastępują podstawki z `tests/fakes.py`.

## Stan

Sprawdzone na żywo 2026-11-21:
- Lista CERT Polska: 126 642 domeny wczytane w 13 s.
- Microsoft Ad Library: 20 reklam z Polski, pobrane strony docelowe, 713 markerów, 7 krawędzi, 3 kampanie.
- Analiza zlecona przez API wykonana przez Temporal, postęp odebrany przez SSE, dowody w S3.
- Projekcja do Neo4j, indeks w OpenSearch, skan z harmonogramu Temporala.

Jeszcze nie ma:
- Crawler to klient HTTP. Widzi przekierowania 3xx i meta refresh, nie wykonuje JavaScriptu. Playwright w piaskownicy wchodzi pod ten sam interfejs.
- Konektor Mety jest napisany według dokumentacji, nie był uruchomiony na żywym tokenie.
- Obraz, wideo, twarz i głos: brak ekstrakcji. Osoby rozpoznawane tylko po wzmiance w tekście.
- Embeddingi tekstu: kolumna i indeks HNSW są, model nie jest podpięty. Podobieństwo tekstu liczy MinHash.
- Wagi modelu par są eksperckie, nie uczone.
- Ochrona przed SSRF sprawdza adres przed połączeniem, ale nie przypina wyniku DNS. Właściwą barierą będzie piaskownica z regułami sieciowymi.

## Zasady pracy

1. `main` zawsze działa. Zmiany przez PR.
2. Gałęzie `feat/<co>`, `fix/<co>`. Małe PR-y.
3. Zmiana API zaczyna się od `docs/api.md` i `frontend/src/lib/api.ts`.
4. Sekrety tylko w `.env`.
