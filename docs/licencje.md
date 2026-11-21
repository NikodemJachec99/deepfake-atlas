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
| redis (klient) | 7.4.1 | MIT | pakiet |
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
| opencv-python-headless (zależność rapidocr) | 5.1.0.95 | Apache-2.0 | pakiet |
| Pillow | 13.0.0 | MIT-CMU | pakiet |
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
| SFace (`face_recognition_sface_2021dec.onnx`, OpenCV Zoo) | wektor twarzy do porównania z bazą referencyjną | Apache-2.0 | jak wyżej; bez modelu analiza działa, tylko bez twarzy (`FACE_MODELS_DOWNLOAD=0` wyłącza pobieranie) |

Nie ma modeli głosu ani modeli językowych.

### Baza referencyjna twarzy

`backend/people/face_refs.json`: dla każdej osoby nazwisko, identyfikator Wikidata, plik z Wikimedia Commons, strona pliku, licencja, autor i wektor SFace (128 liczb). Samych zdjęć w repozytorium nie ma. Zdjęcie bierzemy z właściwości P18 w Wikidata i tylko wtedy, gdy licencja na Commons jest wolna (CC0, CC BY, CC BY-SA, GFDL, domena publiczna). Bazę odtwarza `python manage.py build_face_refs`.

Porównujemy wyłącznie z tą bazą osób publicznych, jak dopuszcza opis wyzwania (pkt 5). Wektorów twarzy spoza bazy nie zapisujemy, zostaje tylko marker "twarz osoby X" z wynikiem podobieństwa. Przed użyciem poza konkursem trzeba ustalić podstawę prawną przetwarzania danych biometrycznych (RODO art. 9).

## Usługi uruchamiane lokalnie (kontenery)

| Usługa | Rola | Licencja | Źródło |
|---|---|---|---|
| PostgreSQL 16 + rozszerzenie pgvector | baza, wektory | PostgreSQL License | projekt |
| Temporal (serwer deweloperski) | orkiestracja | MIT | projekt |
| RustFS | magazyn S3 | Apache-2.0 | projekt |
| Neo4j Community 5 | projekcja grafu | GPL-3.0 | projekt |
| OpenSearch 2 | pełny tekst | Apache-2.0 | projekt |
| Redis 7 | cache | RSALv2 / SSPLv1 od wersji 7.4 | projekt |

Neo4j, OpenSearch i Redis działają jako osobne usługi. Nasz kod łączy się z nimi przez sieć i nie zawiera ich kodu. Rdzeń (analiza, łączenie, API) potrzebuje tylko PostgreSQL, Temporala i magazynu S3. Redis można zastąpić Valkey (BSD).

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

## Basal (plan, jeszcze nie uruchomiony)

Opcjonalny lokalny model decyzji z [basal.md](basal.md): silnik basal 2.8.1 (Apache-2.0, NOTICE z listą modeli bazowych) i wagi basal-2.0 (Apache-2.0, na bazie Bielik v3 od SpeakLeash, też Apache-2.0). Nic z tego nie jest w repozytorium ani w obrazach kontenerów. Gdy zostanie uruchomiony, dopisujemy tu dokładną rewizję wag.

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
