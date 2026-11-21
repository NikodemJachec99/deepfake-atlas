"""Lista Ostrzeżeń CERT Polska.

Źródło: https://hole.cert.pl/domains/v2/ (dowolny użytek, także komercyjny).
`domains.json` zawiera wpisy z ostatnich 6 miesięcy. Pełna historia od 2020 jest w plikach
`actions_YYYY.log`, po jednym zdarzeniu block/unblock w wierszu.
"""

import json
from collections.abc import Iterable, Iterator
from datetime import datetime

import httpx

from enrichment.models import WarningDomain

BASE = "https://hole.cert.pl/domains/v2"
BATCH = 5000


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def parse_current(payload: list[dict]) -> Iterator[WarningDomain]:
    for row in payload:
        yield WarningDomain(
            domain=row["DomainAddress"].lower(),
            register_position=row.get("RegisterPositionId"),
            added_at=_dt(row.get("InsertDate")),
            removed_at=_dt(row.get("DeleteDate")),
        )


def _flush(rows: list[WarningDomain], fields: list[str]) -> None:
    # Jedna domena może wystąpić w paczce dwa razy. Postgres nie pozwala na to w jednym upsercie.
    unique = list({row.domain: row for row in rows}.values())
    WarningDomain.objects.bulk_create(unique, update_conflicts=True, unique_fields=["domain"], update_fields=fields)


def store(rows: Iterable[WarningDomain], fields: list[str]) -> int:
    total, batch = 0, []
    for row in rows:
        batch.append(row)
        if len(batch) >= BATCH:
            _flush(batch, fields)
            total += len(batch)
            batch = []
    if batch:
        _flush(batch, fields)
        total += len(batch)
    return total


def sync_current(client: httpx.Client | None = None) -> int:
    client = client or httpx.Client(timeout=120)
    response = client.get(f"{BASE}/domains.json")
    response.raise_for_status()
    return store(parse_current(response.json()), ["register_position", "added_at", "removed_at"])


def parse_actions(lines: Iterable[str]) -> Iterator[tuple[str, WarningDomain]]:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        when = _dt(row["ActionTime"])
        domain = WarningDomain(domain=row["DomainAddress"].lower(), register_position=row.get("RegisterPositionId"))
        if row["ActionType"] == "block":
            domain.added_at, domain.removed_at = when, None  # ponowna blokada kasuje stare wykreślenie
            yield "block", domain
        else:
            domain.removed_at = when
            yield "unblock", domain


def sync_history(year: int, client: httpx.Client | None = None) -> dict:
    """Wczytuje jeden rocznik historii. Wpisy i wykreślenia idą osobno, żeby nie nadpisać sobie dat."""
    client = client or httpx.Client(timeout=300)
    blocks: list[WarningDomain] = []
    unblocks: list[WarningDomain] = []
    with client.stream("GET", f"{BASE}/actions_{year}.log") as response:
        response.raise_for_status()
        for action, row in parse_actions(response.iter_lines()):
            (blocks if action == "block" else unblocks).append(row)
    added = store(blocks, ["register_position", "added_at", "removed_at"])
    removed = store(unblocks, ["removed_at"])
    return {"year": year, "blocked": added, "unblocked": removed}
