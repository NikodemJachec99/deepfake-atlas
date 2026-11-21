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
    verdict_reason = models.CharField(max_length=32, blank=True, default="")
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


class EdgeDecision(models.Model):
    """Jedna decyzja analityka o krawędzi, z powodem i migawką tego, co wtedy widział.

    Dowody krawędzi (`EdgeEvidence`) są przebudowywane przy każdym przeliczeniu, więc migawka jest
    jedynym trwałym zapisem podstawy decyzji. Wpis jest niezmienny: kolejna decyzja to nowy wiersz.
    Krawędź może zniknąć przy przeliczeniu korpusu, dlatego para reklam jest zapisana osobno.
    """

    class Reason(models.TextChoices):
        SHARED_TOOL = "shared_tool", "Wspólne narzędzie albo silnik, nie ślad operatora"
        SHARED_INFRASTRUCTURE = "shared_infrastructure", "Współdzielona infrastruktura (CDN, hosting, rejestrator)"
        EXTRACTION_ERROR = "extraction_error", "Błędna ekstrakcja śladu"
        NO_INDEPENDENT_CONFIRMATION = "no_independent_confirmation", "Brak niezależnego potwierdzenia"
        CONFIRMED_BY_ANALYST = "confirmed_by_analyst", "Analityk potwierdził wspólne źródło"
        OTHER = "other", "Inny powód (w notatce)"
        UNKNOWN = "unknown", "Nieznany (decyzja bez podanego powodu)"

    edge = models.ForeignKey(Edge, null=True, blank=True, on_delete=models.SET_NULL, related_name="decisions")
    ad_a = models.ForeignKey("ads.Ad", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    ad_b = models.ForeignKey("ads.Ad", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    verdict = models.CharField(max_length=10, choices=Edge.Verdict.choices)
    previous_verdict = models.CharField(max_length=10, choices=Edge.Verdict.choices, blank=True, default="")
    reason = models.CharField(max_length=32, choices=Reason.choices, default=Reason.UNKNOWN)
    note = models.TextField(blank=True)
    # Pusta migawka oznacza wpis sprzed pamięci sprzeciwu: wiemy, co zdecydowano, ale nie na jakiej podstawie.
    snapshot = models.JSONField(default=dict, blank=True)
    legacy = models.BooleanField(default=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["edge", "created_at"])]


class AssistSuggestion(models.Model):
    """Sugestia modelu decyzji (Jev, wcześniej lokalny basal) o krawędzi. Doradcza i oddzielna od dowodów.

    Nie wpływa na krawędź, wagi, dowody, grupy ani decyzje analityka. Zapisujemy wersję modelu,
    pytania i skrót stanu, żeby wynik dało się odtworzyć i porównać między wersjami.
    """

    class Status(models.TextChoices):
        OK = "ok", "Odpowiedź modelu"
        ABSTAIN = "abstain", "Model wstrzymał się poniżej progu"
        UNAVAILABLE = "unavailable", "Usługa niedostępna"
        TIMEOUT = "timeout", "Przekroczony czas"
        ERROR = "error", "Błąd albo niepoprawna odpowiedź"
        UNAUTHORIZED = "unauthorized", "Brak albo zły klucz API"
        PAYMENT = "payment", "Brak środków na koncie usługi"
        RATE_LIMITED = "rate_limited", "Przekroczony limit zapytań albo usługa przeciążona"

    edge = models.ForeignKey(Edge, null=True, blank=True, on_delete=models.SET_NULL, related_name="suggestions")
    ad_a = models.ForeignKey("ads.Ad", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    ad_b = models.ForeignKey("ads.Ad", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    task = models.CharField(max_length=32)
    mode = models.CharField(max_length=8)  # shadow albo on, w chwili zapisu
    status = models.CharField(max_length=12, choices=Status.choices)
    answer = models.CharField(max_length=32, blank=True)
    probabilities = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    model = models.CharField(max_length=128, blank=True)  # skonfigurowany, np. jev-1.14.0 (stare wpisy: Remek/basal-2.0-mini)
    revision = models.CharField(max_length=64, blank=True)
    variant = models.CharField(max_length=64, blank=True)  # tryb i kwantyzacja, np. eager-bf16
    served_model = models.CharField(max_length=128, blank=True)  # co podał serwer w odpowiedzi
    question_version = models.CharField(max_length=32)
    state_fingerprint = models.CharField(max_length=64)
    edge_version = models.CharField(max_length=40, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)  # z odpowiedzi usługi, podstawa kosztu
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["edge", "task", "created_at"])]


class Alert(models.Model):
    """Nowy materiał dołączył do grupy, która już była w korpusie.

    Powstaje w etapie cluster, raz na reklamę i rodzaj (ponowne uruchomienie etapów niczego nie dubluje).
    Pierwsza reklama nowej kampanii alertu nie daje: nie było jeszcze z czym jej powiązać.
    """

    class Kind(models.TextChoices):
        JOINED_CAMPAIGN = "joined_campaign", "Nowa odsłona znanej kampanii"
        NEW_CAMPAIGN_KNOWN_OPERATOR = "new_campaign_known_operator", "Nowa kampania znanego operatora"
        JOINED_OPERATOR = "joined_operator", "Reklama połączyła grupy znanego operatora"

    ad = models.ForeignKey("ads.Ad", on_delete=models.CASCADE, related_name="alerts")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    campaign = models.ForeignKey(Campaign, null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts")
    operator = models.ForeignKey(Operator, null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts")
    description = models.CharField(max_length=300, blank=True)
    # Najmocniejsze dowody łączące reklamę z grupą: [{kind, label, family, bits, value}], najwyżej 3.
    evidence = models.JSONField(default=list, blank=True)
    seen = models.BooleanField(default=False)
    seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["ad", "kind"], name="alert_ad_kind")]
        indexes = [models.Index(fields=["seen", "-created_at"])]
