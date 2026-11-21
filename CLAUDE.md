# SCAM DNA: instrukcje dla sesji Claude w tym repo

System łączy fałszywe reklamy w kampanie i operatorów na podstawie wspólnych śladów. Zadanie NASK na HackNation, termin zgłoszenia 22.11.2026 godz. 11:00. Po tym terminie nie wolno zmieniać repo.

Najpierw przeczytaj: `README.md`, `docs/metodyka.md`, `docs/api.md`. Dla frontendu także `frontend/AGENTS.md` i `docs/design-prompt.md`.

## Dwa komputery, jedna kolejka

Nad repo pracują dwa komputery na osobnych kontach. Żeby nie robić tego samego dwa razy, zadania są w GitHub Issues, a narzędzie `scripts/praca.py` pilnuje, kto co robi.

| Rola | Komputer | Strefy | Co wolno |
|---|---|---|---|
| `glowny` | mocny, Windows | backend, dane, infra, docs | wszystko, w tym Docker, import paczek, OCR, modele |
| `koder` | MacBook | frontend | tylko kod w `frontend/`; bez Dockera, bez importu danych, bez modeli |

Rola tej maszyny jest w pliku `.maszyna` (poza gitem). Jeśli go nie ma, poproś użytkownika o `python scripts/praca.py start glowny` albo `start koder --host <IP głównego> --port <port backendu>`. Na Macu polecenie to `python3`.

## "Rób swoje zadania zgodnie z planem"

Gdy użytkownik napisze to zdanie albo coś o tym samym sensie, pracuj w pętli i nie pytaj między zadaniami:

1. `python scripts/praca.py nastepne`
   Bierze następne wolne zadanie tej maszyny albo wraca do rozpoczętego. Wypisuje treść zadania.
2. Zrób zadanie w całości, według sekcji "Gotowe gdy" w jego opisie. Przeczytaj pliki, których dotyczy.
3. Sprawdź swoją pracę:
   - frontend: `npm run lint` i `npm run build` w `frontend/`. Jeśli backend głównego odpowiada, sprawdź ekran na prawdziwych danych.
   - backend: `ruff check .` i `pytest -q` w `backend/` (venv w `backend/.venv`).
4. `python scripts/praca.py oddaj -m "po co ta zmiana"`
   Robi commit, testy, push, PR, czeka na CI i merguje. Zadanie zamyka się samo.
5. Wróć do punktu 1.

Zatrzymaj się dopiero, gdy `nastepne` wypisze `BRAK ZADAŃ`. Wtedy napisz użytkownikowi, co weszło do `main` i co czeka.

Gdy zadania nie da się zrobić (brakuje danych, decyzji albo czegoś od drugiego komputera):
`python scripts/praca.py blokada N "konkretny powód"` i bierz następne. Nie zgaduj i nie rób atrapy.

Gdy do zadania potrzebna jest zmiana po drugiej stronie, załóż dla niej zadanie:
`python scripts/praca.py nowe "tytuł" --strefa backend --p0 --opis "co i po co. Gotowe gdy: ..."`

## Zasady, które chronią przed konfliktami

- **Nie ruszaj plików spoza swojej strefy.** `oddaj` to sprawdza i odmawia.
- **Kontrakt API zmienia tylko główny**: `docs/api.md`, `frontend/src/lib/api.ts`, `backend/api/`. Koder, któremu brakuje pola albo endpointu, zakłada zadanie z `--strefa backend --kontrakt` i w tym czasie robi coś innego.
- **Jedno zadanie, jedna gałąź, jeden PR.** Nie dokładaj do gałęzi rzeczy spoza zadania.
- **Nie zaczynaj zadania z etykietą `robi:` drugiego komputera**, nawet jeśli wydaje się proste.
- Przed dłuższą pracą `python scripts/praca.py status`.

## Uprawnienia w tym repo

Decyzja użytkownika z 21.11.2026: w tym repo sesja sama pushuje gałąź zadania i merguje PR po zielonym CI, przez `scripts/praca.py oddaj`. Nie dotyczy to innych repozytoriów. Nie pushuj prosto na `main` i nie omijaj CI.

Zmiana z 21.11.2026 wieczorem, decyzja użytkownika: GitHub Actions jest wyłączone (billing), działamy bez CI. `oddaj` widzi wyłączony workflow i merguje od razu po testach lokalnych (ruff i pytest w `backend/`, lint i build w `frontend/`). Testów lokalnych nie pomijaj. Dalej nie pushuj prosto na `main`.

Commit i opis PR pisz krótko i rzeczowo: po co zmiana, co sprawdzono, czego nie. Bez dopisków o autorstwie.

## Czego nie wolno

- **Danych organizatora w gicie.** Paczki leżą tylko w `data/raw/` (poza gitem). W testach, przykładach i dokumentach używaj zmyślonych wartości. Wyjątek to `docs/dane-organizatora.md`, przez który repo musi zostać prywatne.
- **Zmyślonych danych w interfejsie.** Frontend pokazuje wyłącznie to, co zwraca API. Ekran bez API oznacz jako niedostępny.
- **Renderowania stron oszustów.** Pokazujemy markery, tekst i zrzuty reklam, surowy HTML tylko do pobrania.
- **Tokenów i kluczy w repo.** Tokeny znalezione w adresach zapisujemy jako skrót.
- **Pobierania stron oszustów na żywo z koderem.** Analizy na żywo i import danych robi tylko główny.

## Gdzie co jest

| Katalog | Zawartość |
|---|---|
| `backend/extractors/` | cechy z URL, HTML, HAR, obrazów, tekstu, OCR |
| `backend/evidence/kinds.py` | rejestr typów markerów i ich siła dowodowa |
| `backend/similarity/` | model par (`fusion.py`), łączenie i grupowanie (`service.py`) |
| `backend/workflows/` | potok analizy, Temporal |
| `backend/collectors/` | import paczek (`bundle.py`), biblioteki reklam, lista CERT |
| `backend/api/` | REST i SSE |
| `frontend/src/lib/api.ts` | typy i klient API |
| `frontend/src/components/` | ekrany |

Na głównym backend działa w kontenerach (`docker compose up -d`), lokalne porty są w `.env`. Koder łączy się z nim przez `NEXT_PUBLIC_API_URL` w `frontend/.env.local`, które ustawia `start koder`.
