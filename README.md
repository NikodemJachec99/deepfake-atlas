# Deepfake Atlas — Kolekcjoner Fejków — HackNation 2026

Wykrywanie kampanii fałszywych reklam z wizerunkami znanych osób (NASK).

**Wymagania zadania i checklista: [docs/wymagania.md](docs/wymagania.md)**

## Stack
- **backend/** — Python 3.12, FastAPI, SQLAlchemy, Postgres (pgvector), Redis
- **frontend/** — Next.js (wygeneruj: `npx create-next-app@latest frontend --ts --app --tailwind --eslint`)
- **docker-compose** — db + redis + backend jedną komendą

## Start (5 min)
```bash
cp .env.example .env
docker compose up -d --build
curl localhost:8000/health        # {"status":"ok"}
```

## Podział pracy (2 osoby)
| Osoba | Zakres |
|---|---|
| A | Pipeline: ingest reklam, OCR, embeddingi obraz+tekst, domeny/WHOIS/crt.sh, klasteryzacja kampanii, API |
| B | Front: wizualizacja kampanii (galaktyka/graf 3D), widok reklama → kampania, demo i pitch |

## Zasady (24h, bez chaosu)
1. `main` zawsze działa — tylko przez PR, nikt nie pushuje bezpośrednio.
2. Gałęzie: `feat/<co>`, `fix/<co>`. Małe PR-y, merge co 1–2h, nie raz na koniec.
3. Kontrakt API ustalacie **najpierw** w `docs/api.md` — wtedy front i back idą równolegle (front na mockach).
4. Sekrety tylko w `.env` (jest w .gitignore). Klucz API w repo = wstyd i rotacja kluczy w środku nocy.
5. O 08:00 w niedzielę feature freeze — od tej pory tylko demo, nagranie zapasowe i pitch.
