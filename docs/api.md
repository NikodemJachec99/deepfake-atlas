# Kontrakt API

Baza: `http://localhost:8000` (port zmienia `BACKEND_PORT`). Schemat OpenAPI: `/api/schema/`, Swagger: `/api/docs/`.
Typy TypeScript i gotowy klient: `frontend/src/lib/api.ts`.

Frontend niczego nie liczy sam. Każda wartość na ekranie pochodzi z tych wywołań.

| Metoda | Ścieżka | Wejście | Wyjście |
|---|---|---|---|
| GET | `/health` | | `{"status":"ok"}` |
| POST | `/api/analyses` | `{"kind":"url"\|"text","value":"..."}` | `Analysis` (201), od razu ze `status: "queued"` |
| GET | `/api/analyses/{id}` | | `Analysis` z `result` per etap |
| GET | `/api/analyses/{id}/events` | `?after=<seq>` | strumień SSE zdarzeń `AnalysisEvent` |
| GET | `/api/ads` | `?source=&campaign=&q=&page=` | strona `AdSummary` |
| GET | `/api/ads/{id}` | | `AdDetail` z genomem (markery w 7 rodzinach) |
| GET | `/api/ads/{id}/edges` | | lista `Edge` malejąco po pewności |
| POST | `/api/ads/{id}/recluster` | | wynik przypisania do kampanii |
| GET | `/api/edges/{id}` | | `EdgeDetail`: obie reklamy i lista dowodów |
| POST | `/api/edges/{id}/verdict` | `{"verdict":"confirmed"\|"rejected"\|"unsure","note":""}` | `EdgeDetail`, wpis w dzienniku audytu |
| GET | `/api/campaigns` | `?page=` | strona `Campaign` z `size` |
| GET | `/api/campaigns/{id}` | | `CampaignDetail`: reklamy, krawędzie, markery rdzeniowe |
| GET | `/api/graph` | `?campaign=<id>` albo `?ad=<id>`, `?limit=` | `{nodes, edges}` dla Sigma.js |
| GET | `/api/kinds` | | słownik rodzin i typów markerów |
| GET | `/api/artifacts/{sha256}` | | surowy dowód jako załącznik (nigdy się nie renderuje) |

## Strumień postępu (SSE)

`event:` to etap, `data:` to `AnalysisEvent`. Etapy w kolejności: `ingest`, `crawl`, `extract`, `enrich`, `fuse`, `cluster`, `end`.
Każdy etap wysyła `started`, dowolną liczbę `info` i `done` albo `error`. Na końcu przychodzi `event: close`.

```
id: 16
event: fuse
data: {"seq":16,"stage":"fuse","status":"info","message":"Powiązanie z reklamą #12: Ta sama kampania",
       "payload":{"edge":8,"other_ad":12,"relation":"same_campaign","probability":1.0,"bits":61.0,
                  "families":{"narr":18.0,"track":18.0,"infra":25.0},
                  "top_evidence":[{"family":"narr","kind":"email","label":"E-mail","value":"odo@tms.pl","bits":18.0}]}}
```

Zdarzenia `fuse/info` przychodzą po jednym na znalezione powiązanie. Graf w trybie Discovery dorysowuje krawędzie w tej kolejności.

## Dowód (`Evidence`)

```json
{
  "family": "track", "family_label": "Tracking i lejek",
  "kind": "ga4", "label": "Google Analytics 4",
  "value_a": "G-7K2QX9LM4T", "value_b": "G-7K2QX9LM4T",
  "similarity": 1.0,
  "df": 2, "corpus_n": 1840,
  "raw_bits": 18.0, "weight_bits": 18.0,
  "decisive": true,
  "artifact_a": "<sha256 HTML strony A>", "artifact_b": "<sha256 HTML strony B>"
}
```

- `df` z `corpus_n`: w ilu niezależnych źródłach występuje ta wartość. Źródłem jest kampania albo reklama bez kampanii.
- `weight_bits`: wkład dowodu po zniżce za korelację w rodzinie. Suma wkładów to `Edge.bits`.
- Markery miękkie (`dom_minhash`, `text_minhash`) mają `df = 0` i podobieństwo w `similarity`.
- `decisive`: rzadki marker rozstrzygający, sam wystarcza do relacji `same_campaign`.

## Relacje

- `same_campaign`: to samo źródło. Wymaga pewności co najmniej 0,9 oraz jednego markera rozstrzygającego albo dwóch niezależnych rodzin.
- `similar`: podobna koncepcja (narracja, kreacja, osoby), bez dowodu wspólnego zaplecza.

## Czego API jeszcze nie ma

Oś czasu kampanii (migawki są w bazie, brakuje endpointu), stan źródeł i skanów, baza osób, kolejka etykietowania, alerty, raporty, role i klucze. Interfejs nie powinien udawać tych danych.
