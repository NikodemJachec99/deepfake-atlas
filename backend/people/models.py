from django.db import models


class Person(models.Model):
    """Osoba publiczna z bazy referencyjnej. Na start rozpoznawana po wzmiance w tekście.

    Kanał twarzy i głosu dochodzi w M4 do M6 i wymaga wcześniej podstawy prawnej dla biometrii.
    """

    name = models.CharField(max_length=255)
    wikidata_id = models.CharField(max_length=16, blank=True, db_index=True)
    aliases = models.JSONField(default=list, blank=True)
    note = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name

    def needles(self) -> list[str]:
        return [n.lower() for n in [self.name, *self.aliases] if len(n) >= 5]

    @property
    def marker_value(self) -> str:
        return self.wikidata_id or f"person:{self.pk}"
