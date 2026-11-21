from django.conf import settings
from django.db import models


class Edge(models.Model):
    class Relation(models.TextChoices):
        SAME_CAMPAIGN = "same_campaign", "Ta sama kampania"
        SAME_OPERATOR = "same_operator", "Ten sam operator"
        SIMILAR = "similar", "Podobna koncepcja"

    class Verdict(models.TextChoices):
        NONE = "", "Bez decyzji"
        CONFIRMED = "confirmed", "Potwierdzone"
        REJECTED = "rejected", "Odrzucone"
        UNSURE = "unsure", "Niepewne"

    # Zawsze ad_a.id < ad_b.id, żeby para miała jedną krawędź.
    ad_a = models.ForeignKey("ads.Ad", on_delete=models.CASCADE, related_name="edges_a")
    ad_b = models.ForeignKey("ads.Ad", on_delete=models.CASCADE, related_name="edges_b")
    relation = models.CharField(max_length=16, choices=Relation.choices)
    bits = models.FloatField()
    probability = models.FloatField()
    decisive = models.BooleanField(default=False)
    # Ta sama strona przechwycona ponownie. Podzbiór relacji same_campaign.
    duplicate = models.BooleanField(default=False)
    families = models.JSONField(default=dict)
    model_version = models.CharField(max_length=16)
    verdict = models.CharField(max_length=10, choices=Verdict.choices, blank=True, default="")
    verdict_note = models.TextField(blank=True)
    verdict_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    verdict_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ad_a", "ad_b"], name="edge_pair"),
            models.CheckConstraint(condition=models.Q(ad_a__lt=models.F("ad_b")), name="edge_ordered"),
        ]

    def other(self, ad_id: int) -> int:
        return self.ad_b_id if self.ad_a_id == ad_id else self.ad_a_id


class EdgeEvidence(models.Model):
    """Jeden dowód stojący za krawędzią. Bez wierszy w tej tabeli krawędź nie ma prawa istnieć."""

    edge = models.ForeignKey(Edge, on_delete=models.CASCADE, related_name="evidence")
    family = models.CharField(max_length=8)
    kind = models.CharField(max_length=32)
    value_a = models.TextField(blank=True)
    value_b = models.TextField(blank=True)
    similarity = models.FloatField(default=1.0)
    df = models.PositiveIntegerField(default=0)
    corpus_n = models.PositiveIntegerField(default=0)
    raw_bits = models.FloatField()
    weight_bits = models.FloatField()
    decisive = models.BooleanField(default=False)
    artifact_a = models.ForeignKey("evidence.Artifact", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    artifact_b = models.ForeignKey("evidence.Artifact", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-weight_bits"]


class Campaign(models.Model):
    label = models.CharField(max_length=256, blank=True)
    merged_into = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="merged_from")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def key(self) -> str:
        return f"K-{self.pk:04d}"

    def __str__(self) -> str:
        return f"{self.key} {self.label}".strip()


class CampaignMembership(models.Model):
    ad = models.OneToOneField("ads.Ad", on_delete=models.CASCADE, related_name="membership")
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="memberships")
    joined_at = models.DateTimeField(auto_now_add=True)


class Operator(models.Model):
    """Wspólne zaplecze kilku kampanii: ten sam silnik lejka, te same identyfikatory, ta sama infrastruktura."""

    label = models.CharField(max_length=256, blank=True)
    merged_into = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="merged_from")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def key(self) -> str:
        return f"O-{self.pk:04d}"

    def __str__(self) -> str:
        return f"{self.key} {self.label}".strip()


class OperatorMembership(models.Model):
    ad = models.OneToOneField("ads.Ad", on_delete=models.CASCADE, related_name="operator_membership")
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="memberships")
    joined_at = models.DateTimeField(auto_now_add=True)
