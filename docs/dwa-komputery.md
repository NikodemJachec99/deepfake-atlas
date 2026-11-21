# Praca na dwóch komputerach

Komputer główny (Windows) trzyma kontenery, dane i ciężkie operacje. MacBook tylko pisze frontend i łączy się z backendem głównego po sieci. Zadania są w GitHub Issues, więc oba komputery widzą ten sam stan od razu, bez czekania na `git pull`.

## Jednorazowo na głównym

```bash
python scripts/praca.py start glowny
```

Polecenie wypisze adres tego komputera w sieci lokalnej. Backend musi być osiągalny z MacBooka, więc w PowerShellu jako administrator:

```powershell
netsh advfirewall firewall add rule name="scamdna-backend" dir=in action=allow protocol=TCP localport=8010
```

Port to `BACKEND_PORT` z pliku `.env` (domyślnie 8000).

## Jednorazowo na MacBooku

```bash
brew install gh node git          # jeśli brakuje
gh auth login                     # to samo konto GitHub, które ma dostęp do repo
git clone https://github.com/NikodemJachec99/deepfake-atlas.git
cd deepfake-atlas
python3 scripts/praca.py start koder --host <IP głównego> --port 8010
cd frontend && npm install && npm run dev      # http://localhost:3000
```

`start koder` zapisuje adres backendu w `frontend/.env.local` i od razu sprawdza, czy odpowiada. Docker na MacBooku nie jest potrzebny.

Jeśli backend nie odpowiada: oba komputery muszą być w tej samej sieci. Sieci gościnne często izolują urządzenia, wtedy podepnij oba do hotspotu z telefonu albo użyj Tailscale i podaj adres z niego jako `--host`.

## Codzienna praca

W Claude Code na dowolnym z komputerów wystarczy napisać:

```
rób swoje zadania zgodnie z planem
```

Sesja czyta `CLAUDE.md`, bierze następne wolne zadanie swojej maszyny, robi je, oddaje i bierze kolejne.

To samo ręcznie:

| Polecenie | Co robi |
|---|---|
| `praca.py status` | co mam w toku, co robi drugi komputer, co jest wolne |
| `praca.py nastepne` | bierze następne wolne zadanie mojej strefy |
| `praca.py oddaj -m "opis"` | commit, testy, push, PR, czeka na CI, merge |
| `praca.py blokada N "powód"` | odkłada zadanie, którego nie da się zrobić |
| `praca.py nowe "tytuł" --strefa backend --p0 --opis "..."` | nowe zadanie, także dla drugiego komputera |
| `praca.py puszczam N` | oddaje zadanie z powrotem do kolejki |
| `praca.py lista --wszystkie` | wolne zadania ze wszystkich stref |

## Jak to pilnuje, żeby nie dublować

- **Blokada zadania.** Wzięcie zadania nakłada etykietę `robi:glowny` albo `robi:koder`. Drugi komputer takiego zadania nie zobaczy na liście i nie da rady go wziąć.
- **Strefy.** Koder bierze tylko `strefa:frontend`, główny resztę. `oddaj` odmawia, gdy zmiany wychodzą poza strefę.
- **Kontrakt API** (`docs/api.md`, `frontend/src/lib/api.ts`) zmienia tylko główny. Koder zgłasza potrzebę zadaniem z etykietą `kontrakt`.
- **Kolejność.** Najpierw `p0`, potem `p1`, w obrębie priorytetu po numerze. Zadanie z linijką `Zależy od: #12` czeka, aż #12 się zamknie.
- **Jedno zadanie w toku na komputer.** `nastepne` najpierw każe dokończyć rozpoczęte.

## Dobre zadanie

Tytuł mówi, co ma powstać. Opis ma trzy rzeczy: po co, czego dotyczy (pliki, endpointy) i linijkę `Gotowe gdy:` z warunkiem, który da się sprawdzić. Bez tego sesja nie wie, kiedy skończyć.
