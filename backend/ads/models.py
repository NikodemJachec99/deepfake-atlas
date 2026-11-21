import uuid

from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField


class Source(models.TextChoices):
    MANUAL = "manual", "Zgłoszenie ręczne"
    META = "meta", "Meta Ad Library"
    GOOGLE = "google", "Google Ads Transparency"
    TIKTOK = "tiktok", "TikTok Commercial Content"
    MICROSOFT = "microsoft", "Microsoft Ad Library"
    NATIVE = "native", "Sieć natywna (crawl wydawcy)"


class Advertiser(models.Model):
    source = models.CharField(max_length=16, choices=Source.choices)
    external_id = models.CharField(max_length=128)
    name = models.CharField(max_length=512, blank=True)
    payer = models.CharField(max_length=512, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "external_id"], name="advertiser_source_extid")]

    def __str__(self) -> str:
        return f"{self.name or self.external_id} ({self.source})"


class Ad(models.Model):
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    external_id = models.CharField(max_length=128, blank=True)
    advertiser = models.ForeignKey(Advertiser, null=True, blank=True, on_delete=models.SET_NULL, related_name="ads")
    title = models.TextField(blank=True)
    text = models.TextField(blank=True)
    landing_url = models.TextField(blank=True)
    display_url = models.TextField(blank=True)
    creative_url = models.TextField(blank=True)
    first_seen = models.DateTimeField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    # Etykiety z zewnątrz, np. obecność domeny na Liście Ostrzeżeń CERT Polska.
    labels = models.JSONField(default=dict, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    text_embedding = VectorField(dimensions=settings.TEXT_EMBEDDING_DIM, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"], condition=~models.Q(external_id=""), name="ad_source_extid"
            )
        ]
        indexes = [
            HnswIndex(
                name="ad_text_embedding_hnsw",
                fields=["text_embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]

    def __str__(self) -> str:
        return f"#{self.pk} {self.title or self.landing_url or self.text[:60]}"


class AdSnapshot(models.Model):
    """Stan reklamy w chwili skanu. Tryb Evolution odtwarza z tego historię, więc nic nie nadpisujemy."""

    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name="snapshots")
    observed_at = models.DateTimeField()
    active = models.BooleanField(default=True)
    content_hash = models.CharField(max_length=40)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["observed_at"]
        indexes = [models.Index(fields=["ad", "observed_at"])]


class Analysis(models.Model):
    class Kind(models.TextChoices):
        URL = "url", "Adres URL"
        TEXT = "text", "Tekst lub nazwa produktu"
        AD = "ad", "Reklama z biblioteki"

    class Status(models.TextChoices):
        QUEUED = "queued", "W kolejce"
        RUNNING = "running", "W toku"
        DONE = "done", "Zakończona"
        FAILED = "failed", "Błąd"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ad = models.ForeignKey(Ad, null=True, blank=True, on_delete=models.SET_NULL, related_name="analyses")
    input_kind = models.CharField(max_length=8, choices=Kind.choices)
    input_value = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.QUEUED)
    # Stan między etapami. Każdy etap czyta go z bazy, więc można go ponowić niezależnie od pozostałych.
    state = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "analyses"


class AnalysisEvent(models.Model):
    """Zdarzenie postępu. Interfejs odtwarza je w tej kolejności, więc animacja pokazuje to, co się stało."""

    analysis = models.ForeignKey(Analysis, on_delete=models.CASCADE, related_name="events")
    seq = models.PositiveIntegerField()
    stage = models.CharField(max_length=16)
    status = models.CharField(max_length=8)  # started | done | info | error
    message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["seq"]
        constraints = [models.UniqueConstraint(fields=["analysis", "seq"], name="analysis_event_seq")]
