import uuid

from django.db import models


class HuntRun(models.Model):
    """Jeden przebieg łowcy: komenda, harmonogram albo `POST /api/hunt/run`. Liczby i błąd zostają po przebiegu."""

    class Status(models.TextChoices):
        QUEUED = "queued", "W kolejce"
        RUNNING = "running", "W toku"
        DONE = "done", "Zakończony"
        FAILED = "failed", "Błąd"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Pusty operator: wszyscy znani operatorzy.
    operator = models.ForeignKey("similarity.Operator", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    params = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.QUEUED)
    # Zapytania do crt.sh, kandydaci, wyniki potwierdzenia, powód przerwania.
    stats = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class HuntCandidate(models.Model):
    """Domena, której jeszcze nie ma w korpusie, a która wygląda jak nowe zaplecze znanego operatora."""

    class Status(models.TextChoices):
        CANDIDATE = "candidate", "Kandydat"
        CONFIRMED = "confirmed", "Potwierdzony"
        REJECTED = "rejected", "Odrzucony"
        UNAVAILABLE = "unavailable", "Niedostępny"

    domain = models.CharField(max_length=255)
    operator = models.ForeignKey("similarity.Operator", on_delete=models.CASCADE, related_name="hunt_candidates")
    # Skąd domena trafiła do kandydatów: `crtsh` (nowy certyfikat), `cert_pl` (Lista Ostrzeżeń CERT Polska).
    sources = models.JSONField(default=list)
    # Certyfikat, po którym znaleźliśmy domenę (najnowszy pasujący). Puste, gdy źródłem jest tylko lista CERT.
    cert_issuer = models.CharField(max_length=300, blank=True)
    cert_serial = models.CharField(max_length=80, blank=True)
    cert_not_before = models.DateTimeField(null=True, blank=True)
    crtsh_id = models.BigIntegerField(null=True, blank=True)
    # Wynik wstępny 0..1 policzony bez sieci do strony i jego składniki (tokeny, szablon, wystawca).
    prelim_score = models.FloatField(default=0.0)
    score_parts = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CANDIDATE)
    # Potwierdzenie przez crawler: suma bitów modelu par i dowody z wkładem każdego.
    bits = models.FloatField(null=True, blank=True)
    probability = models.FloatField(null=True, blank=True)
    evidence = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=300, blank=True)
    final_url = models.TextField(blank=True)
    http_status = models.PositiveIntegerField(null=True, blank=True)
    crawl_error = models.CharField(max_length=300, blank=True)
    html_sha = models.CharField(max_length=64, blank=True)
    screenshot_sha = models.CharField(max_length=64, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    checked_at = models.DateTimeField(null=True, blank=True)

    run = models.ForeignKey(HuntRun, null=True, blank=True, on_delete=models.SET_NULL, related_name="candidates")
    # Zgłoszenie do pełnej analizy: po niej domena jest reklamą w korpusie.
    analysis = models.ForeignKey("ads.Analysis", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["domain", "operator"], name="hunt_candidate_domain_operator")]
        indexes = [models.Index(fields=["status", "-prelim_score"]), models.Index(fields=["operator", "status"])]

    def __str__(self) -> str:
        return f"{self.domain} ({self.get_status_display()})"
