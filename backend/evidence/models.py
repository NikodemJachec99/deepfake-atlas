import hashlib

from django.conf import settings
from django.db import models

from .kinds import FAMILIES, KINDS


class Artifact(models.Model):
    """Surowy dowód (HTML, zrzut, plik kreacji). Kluczem jest hash treści, więc treści nie da się podmienić."""

    sha256 = models.CharField(max_length=64, primary_key=True)
    kind = models.CharField(max_length=32)
    content_type = models.CharField(max_length=128, blank=True)
    size = models.PositiveBigIntegerField()
    storage_key = models.CharField(max_length=256)
    source_url = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Marker(models.Model):
    kind = models.CharField(max_length=32, db_index=True)
    value = models.TextField()
    value_hash = models.CharField(max_length=40, editable=False)
    # Liczba reklam z tym markerem. Z niej liczy się rzadkość, czyli siła dowodu.
    ad_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "value_hash"], name="marker_kind_value")]

    @staticmethod
    def hash_value(value: str) -> str:
        return hashlib.sha1(value.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        self.value_hash = self.hash_value(self.value)
        super().save(*args, **kwargs)

    @property
    def family(self) -> str:
        return KINDS[self.kind].family

    @property
    def family_label(self) -> str:
        return FAMILIES[self.family]

    def __str__(self) -> str:
        return f"{self.kind}={self.value[:80]}"


class AdMarker(models.Model):
    ad = models.ForeignKey("ads.Ad", on_delete=models.CASCADE, related_name="ad_markers")
    marker = models.ForeignKey(Marker, on_delete=models.CASCADE, related_name="ad_markers")
    artifact = models.ForeignKey(Artifact, null=True, blank=True, on_delete=models.SET_NULL)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ad", "marker"], name="admarker_ad_marker")]


class AdSignature(models.Model):
    """Sygnatura MinHash markera miękkiego (szablon strony, tekst)."""

    ad = models.ForeignKey("ads.Ad", on_delete=models.CASCADE, related_name="signatures")
    kind = models.CharField(max_length=32)
    values = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ad", "kind"], name="adsignature_ad_kind")]


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=64)
    object_id = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
