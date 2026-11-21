# Biblioteki, modele, usługi i dane: licencje i ograniczenia

Wymóg z opisu wyzwania (pkt 4): wskazać wykorzystane biblioteki, modele i zewnętrzne usługi wraz z licencjami i ograniczeniami.

Kolumna "Źródło" mówi, skąd pochodzi informacja o licencji: **pakiet** oznacza metadane zainstalowanej wersji (odczytane 2026-11-21), **projekt** oznacza deklarację projektu, której nie weryfikowaliśmy maszynowo.

## Biblioteki Python (backend)

| Pakiet | Wersja | Licencja | Źródło |
|---|---|---|---|
| Django | 5.2.19 | BSD-3-Clause | pakiet |
| djangorestframework | 3.18.3 | BSD-3-Clause | pakiet |
| drf-spectacular | 0.30.0 | BSD-3-Clause | pakiet |
| django-cors-headers | 4.9.0 | MIT | pakiet |
| uvicorn | 0.54.0 | BSD-3-Clause | pakiet |
| watchfiles | 1.3.0 | MIT | pakiet |
| dj-database-url | 3.1.2 | BSD-3-Clause | pakiet |
| psycopg | 3.3.9 | LGPL-3.0-only | pakiet |
| pgvector (klient) | 0.5.1 | MIT | pakiet |
| Playwright (usługa crawler) | 1.65.2 | Apache-2.0 | pakiet w obrazie `crawler` |
| Chromium (usługa crawler) | z Playwright 1.65.2 | BSD-3-Clause i inne licencje otwarte | pobierany przez `playwright install` |
| boto3 | 1.44.9 | Apache-2.0 | pakiet |
| neo4j (sterownik) | 6.4.1 | Apache-2.0 AND Python-2.0 | pakiet |
| opensearch-py | 3.2.0 | Apache-2.0 | pakiet |
| temporalio | 1.36.1 | MIT | pakiet |
| httpx | 0.28.1 | BSD-3-Clause | pakiet |
| tldextract | 5.4.0 | BSD-3-Clause | pakiet |
| dnspython | 2.9.2 | ISC | pakiet |
| mmh3 | 5.3.1 | MIT | pakiet |
| rapidocr | 3.10.0 | Apache-2.0 | pakiet |
| onnxruntime | 1.32.0 | MIT | pakiet |
| tokenizers | 0.x | Apache-2.0 | pakiet |
| opencv-python-headless (zależność rapidocr) | 5.1.0.95 | Apache-2.0 | pakiet |
| Pillow | 13.0.0 | MIT-CMU | pakiet |
| faster-whisper (transkrypcja mowy) | 1.2.1 | MIT | pakiet |
| ctranslate2 (silnik wnioskowania modelu mowy, CPU) | 4.9.0 | MIT | pakiet |
| av (zależność faster-whisper, dołącza biblioteki FFmpeg na LGPL) | 19.0.2 | BSD-3-Clause | pakiet |
| imageio-ffmpeg (wykonywalny ffmpeg do wyciągania dźwięku, uruchamiany jako osobny proces) | 0.8.1 | BSD-2-Clause (opakowanie; sam ffmpeg na LGPL/GPL) | pakiet |
| numpy | 2.5.5 | BSD-3-Clause i pokrewne | pakiet |
| pytest, pytest-django, ruff | 9.2.0, 4.14.0, 0.17.6 | MIT, BSD-3-Clause, MIT | pakiet |

psycopg jest na LGPL: używamy go jako biblioteki bez modyfikacji, co nie nakłada tej licencji na nasz kod.

## Biblioteki JavaScript (frontend)

| Pakiet | Wersja | Licencja | Źródło |
|---|---|---|---|
| next | 16.4.6 | MIT | pakiet |
| react, react-dom | 19.3.0 | MIT | pakiet |
| tailwindcss, @tailwindcss/turbopack | 4.3.3 | MIT | pakiet |
| typescript | 5.9.3 | Apache-2.0 | pakiet |
| eslint, eslint-config-next | 9.39.5, 16.4.6 | MIT | pakiet |

## Modele

| Model | Do czego | Licencja | Ograniczenia |
|---|---|---|---|
| PP-OCRv5 (detekcja i rozpoznawanie, alfabet łaciński), przez RapidOCR | tekst ze zrzutów reklam | Apache-2.0 (projekt) | pobierany przy pierwszym użyciu, działa lokalnie, niczego nie wysyła na zewnątrz |
| YuNet (`face_detection_yunet_2023mar.onnx`, OpenCV Zoo) | wykrywanie twarzy na zrzutach reklam | MIT | pobierany przy pierwszym użyciu do `data/models/`, działa lokalnie na CPU |
| paraphrase-multilingual-MiniLM-L12-v2 (sentence-transformers), wersja ONNX int8 z `Xenova/paraphrase-multilingual-MiniLM-L12-v2` | wektor znaczenia treści strony (384 liczby), podobieństwo parafraz | Apache-2.0 | pobierany przy pierwszym użyciu do `data/models/minilm/` (118 MB), działa lokalnie na CPU; `EMBEDDINGS_DOWNLOAD=0` wyłącza pobieranie |
| CLIP ViT-B/32 (OpenAI), część obrazowa w ONNX int8 z `Xenova/clip-vit-base-patch32` (`onnx/vision_model_quantized.onnx`) | wektor obrazu reklamy (512 liczb), podobne ujęcie | MIT | pobierany przy pierwszym użyciu do `data/models/clip/` (89 MB), działa lokalnie na CPU; `EMBEDDINGS_DOWNLOAD=0` wyłącza pobieranie; bez nowych bibliotek (onnxruntime, Pillow, numpy); zero-shot do logo marek nie działa na naszych danych, więc części tekstowej modelu nie używamy |
| Whisper `small` (OpenAI, wagi 244 mln parametrów) w konwersji CTranslate2 `Systran/faster-whisper-small`, język `pl` | transkrypcja mowy z nagrań reklam do tekstu reklamy | MIT (wagi OpenAI i konwersja Systran) | pobierany przy pierwszym użyciu do `data/models/whisper/` (ok. 0,5 GB), działa lokalnie na CPU w int8; `TRANSCRIBE=off` wyłącza kanał, `TRANSCRIBE_DOWNLOAD=0` wyłącza pobieranie; model `base` (`TRANSCRIBE_MODEL=base`) jest 2,5 razy szybszy, ale myli się wyraźnie częściej; Whisper bywa, że halucynuje na ciszy i muzyce, więc odrzucamy segmenty o wysokim prawdopodobieństwie braku mowy |
| SFace (`face_recognition_sface_2021dec.onnx`, OpenCV Zoo) | wektor twarzy do porównania z bazą referencyjną | Apache-2.0 | jak wyżej; bez modelu analiza działa, tylko bez twarzy (`FACE_MODELS_DOWNLOAD=0` wyłącza pobieranie) |

Model mowy działa lokalnie i niczego nie wysyła na zewnątrz. Nie ma modeli rozpoznawania mówcy (klonu głosu) ani generatywnych modeli językowych.

### Baza referencyjna twarzy

`backend/people/face_refs.json`: dla każdej osoby nazwisko, identyfikator Wikidata, plik z Wikimedia Commons, strona pliku, licencja, autor i wektor SFace (128 liczb). Samych zdjęć w repozytorium nie ma. Zdjęcie bierzemy z właściwości P18 w Wikidata i tylko wtedy, gdy licencja na Commons jest wolna (CC0, CC BY, CC BY-SA, GFDL, domena publiczna). Bazę odtwarza `python manage.py build_face_refs`. Gdy zdjęcie z Wikidata nie ma wolnej licencji, builder szuka w kategorii osoby na Commons (z podkategoriami) portretu z jedną twarzą na wolnej licencji i przyjmuje go tylko wtedy, gdy zgadza się z drugim niezależnym zdjęciem. Plik można też wskazać ręcznie: `--file "Osoba=File:..."`.

Porównujemy wyłącznie z tą bazą osób publicznych, jak dopuszcza opis wyzwania (pkt 5). Wektorów twarzy spoza bazy nie zapisujemy, zostaje tylko marker "twarz osoby X" z wynikiem podobieństwa. Przed użyciem poza konkursem trzeba ustalić podstawę prawną przetwarzania danych biometrycznych (RODO art. 9).

## Usługi uruchamiane lokalnie (kontenery)

| Usługa | Rola | Licencja | Źródło |
|---|---|---|---|
| PostgreSQL 16 + rozszerzenie pgvector | baza, wektory | PostgreSQL License | projekt |
| Temporal (serwer deweloperski) | orkiestracja | MIT | projekt |
| RustFS | magazyn S3 | Apache-2.0 | projekt |
| Neo4j Community 5 | projekcja grafu | GPL-3.0 | projekt |
| OpenSearch 2 | pełny tekst | Apache-2.0 | projekt |

Neo4j i OpenSearch działają jako osobne usługi. Nasz kod łączy się z nimi przez sieć i nie zawiera ich kodu. Rdzeń (analiza, łączenie, API) potrzebuje tylko PostgreSQL, Temporala i magazynu S3. Redisa nie używamy: obraz od wersji 7.4 ma licencję RSALv2/SSPLv1, która nie jest licencją otwartą, a kod go nie potrzebował, więc usunęliśmy go z compose 22.11.

## Zewnętrzne usługi i dane

| Usługa | Do czego | Dostęp | Ograniczenia |
|---|---|---|---|
| Lista Ostrzeżeń CERT Polska (`hole.cert.pl`) | etykieta domeny | bez klucza | dowolny użytek; bez sugerowania związku z NASK |
| RDAP rejestru .pl (`rdap.dns.pl`), `rdap.org` | dane rejestrowe domen | bez klucza | dane osób fizycznych zamaskowane |
| crt.sh (Sectigo) | certyfikaty domeny z dzienników CT | bez klucza | serwis bywa wolny i ogranicza ruch; pytamy co 3 s, odpowiedź trzymamy 7 dni |
| Team Cymru IP→ASN | numer AS | bez klucza, zapytania DNS | tylko strony badane na żywo |
| Wikidata, Wikimedia Commons API | zdjęcia do bazy referencyjnej twarzy, tylko przy `build_face_refs` | bez klucza | tylko pliki na wolnej licencji, autor i licencja zapisane przy każdym wektorze |
| Microsoft Ad Library API | reklamy z adresem docelowym | bez klucza | ostre limity zapytań bez konta |
| Meta Ad Library API | reklamy z UE | **wymaga tokenu**: weryfikacja tożsamości na facebook.com/ID, aplikacja deweloperska, token w `META_AD_LIBRARY_TOKEN` | tylko oficjalne API, scraping webowej biblioteki jest zabroniony; konektor nie był uruchomiony na żywym tokenie |

Żadna z tych usług nie jest potrzebna do analizy materiałów z przechwyceń. Bez dostępu do sieci system nadal importuje sprawy i łączy je, traci tylko dane RDAP i certyfikaty z crt.sh. Do oceny nie trzeba żadnych kluczy.

## Jev (TypeSafe) i archiwalny basal

[Jev](jev.md) to zewnętrzna usługa TypeSafe, płatna za tokeny wejściowe, hostowana w USA. Domyślnie wyłączona, a do wysyłki pochodnych danych spraw potrzebna jest osobna zgoda (`JEV_ALLOW_CASE_DATA`). Kodu ani wag TypeSafe nie ma w repozytorium. Klucz API trzymamy tylko w `.env`.

Wcześniejszy wariant, lokalny basal ([basal.md](basal.md), archiwum): silnik basal 2.8.1 (Apache-2.0) i wagi basal-2.0 (Apache-2.0, na bazie Bielik v3 od SpeakLeash). Pomiar 21.11.2026 robiliśmy w osobnym środowisku poza repo. W repozytorium ani w obrazach kontenerów nic z tego nie ma.

## Materiały organizatora

Zgodnie z pkt 8 opisu wyzwania materiały wolno wykorzystywać wyłącznie na potrzeby wyzwania i nie wolno ich publicznie rozpowszechniać. Dlatego:

- paczki leżą tylko lokalnie w `data/raw/`, katalog jest wyłączony z gita,
- testy i przykłady w repo używają zmyślonych wartości,
- `docs/dane-organizatora.md` opisuje wyniki i wymienia domeny ze spraw, więc **repozytorium musi pozostać prywatne**, z dostępem tylko dla organizatora.

## Narzędzia i zasoby użyte przy pisaniu kodu

- Kod powstał w trakcie wydarzenia z pomocą asystenta programowania Claude Code (Anthropic).
- Szkielet interfejsu wygenerowało `create-next-app`.
- Przed startem wydarzenia (21.11, godz. 10:09) w repo był tylko pusty szkielet: FastAPI z jednym endpointem `/health` i plik compose z bazą. Został w całości zastąpiony kodem napisanym w trakcie wydarzenia.
- Nie używaliśmy cudzego kodu poza bibliotekami wymienionymi wyżej.
