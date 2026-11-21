# Zależności i licencje

Projekt stoi na otwartym oprogramowaniu. Zanim cokolwiek dodasz, dopisz to tutaj z licencją.

Licencje w tabelach są wpisane z pamięci. Przed zgłoszeniem projektu potwierdź je w repozytoriach źródłowych.

Regulaminu hackathonu nie ma w repo. Zasady dotyczące gotowych bibliotek, modeli i danych trzeba sprawdzić na platformie wydarzenia.

## Używane teraz

| Składnik | Rola | Licencja |
|---|---|---|
| Django, Django REST Framework, drf-spectacular, django-cors-headers | API | BSD-3-Clause, BSD |
| PostgreSQL, pgvector | baza, wektory | PostgreSQL License |
| psycopg | sterownik | LGPL-3.0 |
| Temporal (serwer i SDK Python) | orkiestracja | MIT |
| RustFS | magazyn S3 | Apache-2.0 |
| Neo4j Community | projekcja grafu | GPL-3.0 (usługa obok, bez linkowania) |
| OpenSearch, opensearch-py | pełny tekst | Apache-2.0 |
| Redis 7 | cache | RSALv2 / SSPLv1 od wersji 7.4 (usługa obok); zamiennik na BSD: Valkey |
| httpx, dnspython, tldextract, mmh3 | kolekcja i ekstrakcja | BSD, ISC, BSD, MIT |
| boto3 | klient S3 | Apache-2.0 |
| Next.js, React, Tailwind CSS | frontend | MIT |
| pytest, pytest-django, ruff | testy | MIT, BSD, MIT |

## Dane

| Źródło | Warunki |
|---|---|
| Lista Ostrzeżeń CERT Polska | dowolny użytek, także komercyjny; bez sugerowania związku z NASK |
| dns.pl RDAP | publiczne, dane osób fizycznych zamaskowane |
| Microsoft Ad Library API | publiczne API, limity bez konta |
| Meta Ad Library API | tylko oficjalne API; scraping webowej biblioteki jest zabroniony regulaminem |
| Team Cymru IP→ASN | darmowe zapytania DNS |

## Planowane, do sprawdzenia przed dodaniem

| Składnik | Uwaga |
|---|---|
| Qwen3-Embedding, Bielik, PLLuM-12B | Apache-2.0 |
| parakeet-tdt-0.6b-v3 | CC-BY-4.0 |
| PDQ (ThreatExchange), SSCD | BSD, MIT (licencja wag SSCD do potwierdzenia) |
| Phishpedia | CC0 |
| InsightFace (modele) | tylko niekomercyjne, nie używamy bez licencji |
| leidenalg | GPL-3.0, zamiast niego cuGraph albo składowe spójne |
| Sigma.js, Graphology | MIT |
