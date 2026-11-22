# SCAM DNA: interfejs

Interfejs analityka SCAM DNA w Next.js 16 (App Router), React 19, TypeScript i Tailwind 4. Nic nie liczy sam: każda wartość na ekranie pochodzi z API backendu (`../docs/api.md`). Ekran bez odpowiedzi API pokazuje stan niedostępny, nigdy wymyślone dane.

## Uruchomienie

Najprościej całość, razem z backendem, z katalogu głównego repozytorium:

```bash
python scripts/start.py
```

Interfejs działa wtedy na http://localhost:3000.

Sam interfejs w trybie deweloperskim, przy działającym backendzie:

```bash
cd frontend
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Na Windowsie w PowerShellu zmienną ustaw przed poleceniem: `$env:NEXT_PUBLIC_API_URL="http://localhost:8000"; npm run dev`. Adres API można też wpisać do `frontend/.env.local`.

## Sprawdzenie przed oddaniem zmian

```bash
npm run lint
npm run build
```

Oba polecenia uruchamia też `python scripts/praca.py oddaj` przed scaleniem zmian.

## Ekrany

| Ekran | Ścieżka | Co robi |
|---|---|---|
| Do oceny | `/review` | kolejka par z powodem uwagi, stanowisko oceny, zakwestionowanie przesłanki, laboratorium dowodów |
| Analiza | `/` | adres, tekst albo pliki (zrzut, HAR, nagranie, ZIP sprawy), przebieg etapów na żywo, wynik z dowodami |
| Śledztwo | `/investigation` | graf reklam, kampanii i operatorów (sigma.js), lista powiązań, panel dowodów |
| Kampanie, Operatorzy | `/campaigns`, `/operators` | grupy, „Dlaczego razem”, pakiet dowodowy ZIP |
| Archiwum, karta reklamy | `/archive`, `/ads/{id}` | genom reklamy, zrzuty z powiększeniem, podsumowanie HAR, nagrania, obserwacje |
| Alerty | `/alerts` | nowe materiały w znanych grupach |
| Łowca domen | `/hunt` | kandydaci z logów CT i Listy CERT, potwierdzenia |
| Wagi markerów | `/weights` | siła śladów, wagi eksperckie i uczone |
| Zakwestionowania | `/premises` | historia zakwestionowanych przesłanek |

## Struktura

| Miejsce | Zawartość |
|---|---|
| `src/app/` | trasy ekranów, `layout.tsx`, `globals.css` (tokeny marki i kolory rodzin śladów), `icon.svg` (favicon) |
| `src/components/` | ekrany i komponenty: graf, panel dowodów, genom, stanowisko oceny, podsumowanie HAR, powiększanie zdjęć |
| `src/lib/api.ts` | typy i klient API, jedyne miejsce kontraktu z backendem |
| `src/lib/expert.tsx` | tryb prosty i „Szczegóły techniczne” (wybór zapisany w przeglądarce) |

Zasady pracy nad interfejsem: [AGENTS.md](AGENTS.md). Opis całego systemu: [README.md](../README.md).
