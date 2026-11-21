"""Czytelna etykieta wartości markera. Osoby są zapisane jako `person:<id>` (albo identyfikator Wikidata),
a analityk powinien zobaczyć nazwisko. Sama wartość markera się nie zmienia."""

from people.models import Person

PERSON_KINDS = frozenset({"person_mention", "face_match"})


def person_names() -> dict[str, str]:
    names = {}
    for person in Person.objects.only("id", "name", "wikidata_id"):
        names[f"person:{person.pk}"] = person.name
        if person.wikidata_id:
            names[person.wikidata_id] = person.name
    return names


def display_value(kind: str, value: str, names: dict[str, str] | None = None) -> str:
    if kind not in PERSON_KINDS:
        return value
    names = person_names() if names is None else names
    return names.get(value, value)
