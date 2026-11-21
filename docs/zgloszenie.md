# Zgłoszenie na HackTribe: teksty do wklejenia

Szkic projektu trzeba założyć **21.11 przed 20:00** (później nie da się utworzyć projektu ani zmienić zadania). Zgłoszenie końcowe do **22.11 godz. 11:00**. Po tym terminie repozytorium zostaje bez zmian.

Zespół: jedna osoba (Nikodem). Repozytorium jest prywatne, bo `docs/dane-organizatora.md` opisuje sprawy z paczki organizatora. Organizatorowi trzeba nadać dostęp do odczytu albo przekazać kod w inny sposób ([wymagania.md](wymagania.md)).

## Nazwa

SCAM DNA

## Zadanie

NASK, "Kolekcjoner fejków" (Follow the Fake)

## Krótki opis (1–2 zdania)

SCAM DNA łączy pozornie niezależne fałszywe reklamy w kampanie i operatorów na podstawie wspólnych śladów technicznych i treści. Każde połączenie ma listę dowodów z wkładem w bitach, więc da się je sprawdzić i podważyć.

## Opis

Z każdego materiału (adres, zrzut reklamy, zapisana strona, HAR, archiwum NASK, ZIP sprawy) system wyciąga ok. 50 typów markerów w 7 rodzinach: infrastruktura, tracking i lejek, szablon strony, kreacja, narracja, osoby i marki, zachowanie. Parę materiałów ocenia model Fellegi-Sunter z ważeniem rzadkością: adres z puli Cloudflare jest wart ułamek bita, identyfikator strony w panelu lejka 18 bitów. Wspólne źródło wymaga rzadkiego markera albo dwóch niezależnych potwierdzeń, z których jedno dotyczy zaplecza, więc skopiowana treść, wspólna twarz celebryty ani kupiony silnik lejka nie sklejają różnych operatorów.

Wynik to trzy relacje (ta sama kampania, ten sam operator, podobna koncepcja), kampanie i operatorzy jako składowe grafu oraz ocena nowego materiału: duplikat, nowa odsłona znanej kampanii, nowa kampania znanego operatora, tylko podobieństwo albo nowy wzorzec.

Na danych organizatora (28 stron z 25 spraw) system bez podpowiedzi znalazł operatora z 8 stronami na 7 domenach w 2 kampaniach, spiętego identyfikatorami z panelu lejka i pikselem Meta, drugiego operatora z 3 stronami i kampanię z dwiema różnymi stronami pod tym samym adresem. Każdą krawędź między sprawami przejrzeliśmy ręcznie.

Dodatkowo: laboratorium dowodów (co zostaje z połączenia po wyłączeniu śladów i test najsłabszego ogniwa), wskazówki "co sprawdzić dalej", porównanie dwóch przechwyceń tego samego adresu, twarze z małej bazy referencyjnej, eksport wzbogaconego korpusu, Lista Ostrzeżeń CERT Polska, crt.sh, RDAP, konektory bibliotek reklam i harmonogram skanów.

## Technologie

Python 3.12, Django 5.2, DRF, Temporal, PostgreSQL 16 z pgvector, RustFS (S3), Neo4j, OpenSearch, RapidOCR (PP-OCRv5), OpenCV YuNet i SFace, Next.js 16, React 19, TypeScript, Tailwind 4, Sigma.js, Docker Compose.

## Repozytorium

https://github.com/NikodemJachec99/deepfake-atlas (prywatne, dostęp dla organizatora)

## Jak sprawdzić

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec backend python manage.py seed_people
docker compose exec backend python manage.py collect cert_pl
docker compose exec backend python manage.py import_bundle /data/raw/nask --name nask
```

Interfejs: http://localhost:3000. Szczegóły i porty: [README.md](../README.md). Sprawdzone na świeżym klonie na Windowsie i na Linuksie, CI stawia cały stos przy każdym PR.

## Dokumenty dla jury

| Co | Gdzie |
|---|---|
| metodyka: cechy, podobieństwo, grupowanie | [metodyka.md](metodyka.md) |
| wyniki na danych organizatora | [dane-organizatora.md](dane-organizatora.md) |
| zgodność z wymaganiami i kryteriami | [wymagania.md](wymagania.md) |
| prezentacja i scenariusz demo | [prezentacja.md](prezentacja.md) |
| biblioteki, modele, usługi i licencje | [licencje.md](licencje.md) |
| kontrakt API | [api.md](api.md) |

## Załączniki do zgłoszenia końcowego

- prezentacja na 5 minut (plan slajdów w [prezentacja.md](prezentacja.md)),
- nagranie demo do 2 minut: scenariusz z sekcji "Scenariusz demo" w tym samym pliku,
- link do repozytorium z dostępem dla organizatora.
