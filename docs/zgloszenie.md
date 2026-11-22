# Zgłoszenie na HackTribe: teksty do wklejenia

Szkic projektu trzeba założyć **21.11 przed 20:00** (później nie da się utworzyć projektu ani zmienić zadania). Zgłoszenie końcowe do **22.11 godz. 11:00**. Po tym terminie repozytorium zostaje bez zmian.

Zespół: dwie osoby, Nikodem i Sokół. Surowe paczki organizatora są poza gitem, a `docs/dane-organizatora.md` opisuje wyniki na sprawach z paczki ([wymagania.md](wymagania.md)).

## Nazwa

SCAM DNA

## Zadanie

NASK, "Kolekcjoner fejków" (Follow the Fake)

## Krótki opis (1–2 zdania)

SCAM DNA łączy pozornie niezależne fałszywe reklamy w kampanie i operatorów na podstawie wspólnych śladów technicznych i treści. Każde połączenie ma listę dowodów z wkładem w bitach, więc da się je sprawdzić i podważyć.

## Opis

Z każdego materiału (adres, zrzut reklamy, zapisana strona, HAR, archiwum NASK, ZIP sprawy) system wyciąga 62 typy markerów w 7 rodzinach: infrastruktura, tracking i lejek, szablon strony, kreacja, narracja, osoby i marki, zachowanie. Parę materiałów ocenia model Fellegi-Sunter z ważeniem rzadkością: adres z puli Cloudflare jest wart ułamek bita, identyfikator strony w panelu lejka 18 bitów. Wspólne źródło wymaga rzadkiego markera albo dwóch niezależnych potwierdzeń, z których jedno dotyczy zaplecza, więc skopiowana treść, wspólna twarz celebryty ani kupiony silnik lejka nie sklejają różnych operatorów.

Wynik to trzy relacje (ta sama kampania, ten sam operator, podobna koncepcja), kampanie i operatorzy jako składowe grafu oraz ocena nowego materiału: duplikat, nowa odsłona znanej kampanii, nowa kampania znanego operatora, tylko podobieństwo albo nowy wzorzec.

Na danych organizatora (28 stron z 25 spraw) system bez podpowiedzi znalazł operatora z 8 stronami na 7 domenach w 2 kampaniach, spiętego identyfikatorami z panelu lejka i pikselem Meta, drugiego operatora z 3 stronami i kampanię z dwiema różnymi stronami pod tym samym adresem. Każdą krawędź między sprawami przejrzeliśmy ręcznie.

Analityk pracuje na stanowisku oceny: kolejka par z powodem uwagi ("wspólne zaplecze do potwierdzenia", "podobna treść bez wspólnego zaplecza"), porównanie materiałów A i B, najważniejsze przesłanki z ograniczeniami i ocena przypisana do konkretnej wersji dowodów. Odrzucenie mostu rozdziela kampanię i operatora. Analityk może też zakwestionować przesłankę w całym korpusie (np. identyfikator, który okazał się wspólnym pośrednikiem): podgląd pokazuje, które grupy się rozpadną, a które trzymają się na niezależnych śladach, zapis przelicza krawędzie i grupy, przywrócenie je cofa, historia zostaje.

Dodatkowo: crawler z przeglądarką w odizolowanym kontenerze (wyjście tylko przez proxy wpuszczające adresy publiczne, HAR i zrzut strony z wykonanym JavaScriptem), łowca domen (nowe certyfikaty z logów CT pasujące do wzorców znanych operatorów, potwierdzane crawlerem), alerty o nowych materiałach znanych kampanii, pakiet dowodowy operatora i kampanii (raport, artefakty z sumami SHA-256, STIX, skrypt weryfikacji), laboratorium dowodów i test najsłabszego ogniwa, porównanie dwóch przechwyceń tego samego adresu, twarze z małej bazy referencyjnej, nagrania reklam (klatki: OCR, twarze, hash; mowa zamieniona na tekst lokalnym modelem Whisper), podobne ujęcie (CLIP) i podobieństwo znaczenia treści, wagi uczone metodą EM do porównania z eksperckimi, Lista Ostrzeżeń CERT Polska, crt.sh, RDAP, konektory bibliotek reklam i harmonogram skanów.

Wynik sprawdziliśmy liczbowo. Bez plików HAR zostaje 18 z 32 połączeń wspólnego źródła, bez zapisu strony 30, bez zrzutów 32 (model `fs-5.1`, 22.11), a w żadnym wariancie nie powstaje fałszywe połączenie. Zmiana wag modelu o ±50% rusza tylko 4 pary graniczne, a szansa wstępna i próg pewności nie zmieniają żadnej relacji. W próbie "spróbuj zgubić kampanię" (prawdziwy upload na osobnym stosie) 7 z 7 przebranych wariantów (przycięty i przekompresowany zrzut, zmieniony tekst, nowa domena) wróciło do swojej kampanii i operatora, a kopia zrzutu i tekstu na obcej infrastrukturze dała tylko podobieństwo, bez wspólnego operatora.

## Technologie

Python 3.12, Django 5.2, DRF, Temporal, PostgreSQL 16 z pgvector, RustFS (S3), Neo4j, OpenSearch, Playwright z Chromium, RapidOCR (PP-OCRv5), OpenCV YuNet i SFace, paraphrase-multilingual-MiniLM-L12-v2 (ONNX), CLIP ViT-B/32 (ONNX), Whisper small (faster-whisper), Next.js 16, React 19, TypeScript, Tailwind 4, Sigma.js, Docker Compose.

## Repozytorium

https://github.com/NikodemJachec99/deepfake-atlas

## Jak sprawdzić

Paczki rozpakowane do `data/raw/<nazwa>/`, potem:

```bash
python scripts/start.py
```

Skrypt stawia wszystkie usługi, wczytuje bazę osób i importuje paczki. Interfejs: http://localhost:3000, ekran "Do oceny" to stanowisko analityka. Szczegóły i porty: [README.md](../README.md). Sprawdzone na świeżym klonie na Windowsie (obie paczki: 28 reklam, 4 kampanie, 3 operatorów) i wcześniej na Linuksie. Każda zmiana w repo przechodziła lokalnie ruff, pytest, lint i build frontendu po scaleniu z main.

## Dokumenty dla jury

| Co | Gdzie |
|---|---|
| metodyka: cechy, podobieństwo, grupowanie | [metodyka.md](metodyka.md) |
| wyniki na danych organizatora | [dane-organizatora.md](dane-organizatora.md) |
| zgodność z wymaganiami i kryteriami | [wymagania.md](wymagania.md) |
| prezentacja i scenariusz demo | [prezentacja.md](prezentacja.md) |
| biblioteki, modele, usługi i licencje | [licencje.md](licencje.md) |
| plan rozwoju na rok | [plan-roczny.md](plan-roczny.md) |
| kontrakt API | [api.md](api.md) |

## Załączniki do zgłoszenia końcowego

- prezentacja na 5 minut (plan slajdów w [prezentacja.md](prezentacja.md)),
- nagranie demo do 2 minut: scenariusz z sekcji "Scenariusz demo" w tym samym pliku,
- link do repozytorium z dostępem dla organizatora.
