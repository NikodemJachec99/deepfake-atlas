from rest_framework import serializers

from ads.models import Ad, Analysis, AnalysisEvent
from evidence.kinds import BAND_KINDS, FAMILIES, KINDS
from similarity.models import Campaign, Edge, EdgeDecision, EdgeEvidence, Operator


class AnalysisCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[Analysis.Kind.URL, Analysis.Kind.TEXT])
    value = serializers.CharField(max_length=20000, trim_whitespace=True)

    def validate(self, attrs):
        if attrs["kind"] == Analysis.Kind.URL and not attrs["value"].lower().startswith(("http://", "https://")):
            raise serializers.ValidationError({"value": "Adres musi zaczynać się od http:// albo https://"})
        return attrs


class AnalysisEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisEvent
        fields = ["seq", "stage", "status", "message", "payload", "created_at"]


class AnalysisSerializer(serializers.ModelSerializer):
    events_url = serializers.SerializerMethodField()

    class Meta:
        model = Analysis
        fields = ["id", "ad", "input_kind", "input_value", "status", "result", "error", "created_at", "finished_at", "events_url"]

    def get_events_url(self, obj) -> str:
        return f"/api/analyses/{obj.pk}/events"


class AdListSerializer(serializers.ModelSerializer):
    campaign = serializers.SerializerMethodField()
    operator = serializers.SerializerMethodField()
    case = serializers.SerializerMethodField()

    class Meta:
        model = Ad
        fields = ["id", "source", "external_id", "title", "landing_url", "first_seen", "last_seen", "labels", "campaign", "operator", "case"]

    def get_campaign(self, obj) -> str | None:
        membership = getattr(obj, "membership", None)
        return membership.campaign.key if membership else None

    def get_operator(self, obj) -> str | None:
        membership = getattr(obj, "operator_membership", None)
        return membership.operator.key if membership else None

    def get_case(self, obj) -> str | None:
        return obj.labels.get("case")


class AdDetailSerializer(AdListSerializer):
    advertiser = serializers.SerializerMethodField()
    genome = serializers.SerializerMethodField()
    creatives = serializers.SerializerMethodField()

    class Meta(AdListSerializer.Meta):
        fields = [*AdListSerializer.Meta.fields, "text", "display_url", "creative_url", "advertiser", "creatives", "genome"]

    def get_advertiser(self, obj) -> dict | None:
        a = obj.advertiser
        if a:
            return {"id": a.pk, "external_id": a.external_id, "name": a.name, "payer": a.payer}
        name = obj.raw.get("advertiser_name") if isinstance(obj.raw, dict) else ""
        return {"id": None, "external_id": "", "name": name, "payer": ""} if name else None

    def get_creatives(self, obj) -> list[str]:
        """Skróty SHA-256 zrzutów reklamy. Obraz pobiera się z `/api/artifacts/{sha}/image`."""
        return list(obj.raw.get("creatives", [])) if isinstance(obj.raw, dict) else []

    def get_genome(self, obj) -> list[dict]:
        """Markery reklamy pogrupowane w siedem rodzin. Pasma LSH są techniczne, więc ich nie pokazujemy."""
        by_family: dict[str, list[dict]] = {code: [] for code in FAMILIES}
        for am in obj.ad_markers.select_related("marker").all():
            marker = am.marker
            if marker.kind in BAND_KINDS:
                continue
            by_family[marker.family].append(
                {
                    "kind": marker.kind,
                    "label": KINDS[marker.kind].label,
                    "value": marker.value,
                    "ad_count": marker.ad_count,
                    "decisive": KINDS[marker.kind].decisive,
                    "artifact": am.artifact_id,
                    "detail": am.detail,
                }
            )
        return [{"family": code, "label": FAMILIES[code], "markers": items} for code, items in by_family.items()]


class EdgeEvidenceSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    family_label = serializers.SerializerMethodField()

    class Meta:
        model = EdgeEvidence
        fields = [
            "id", "family", "family_label", "kind", "label", "value_a", "value_b", "similarity", "df", "corpus_n",
            "raw_bits", "weight_bits", "decisive", "artifact_a", "artifact_b",
        ]

    def get_label(self, obj) -> str:
        return KINDS[obj.kind].label

    def get_family_label(self, obj) -> str:
        return FAMILIES[obj.family]


class EdgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edge
        fields = ["id", "ad_a", "ad_b", "relation", "duplicate", "bits", "probability", "decisive", "families", "model_version", "verdict", "updated_at"]


class EdgeDetailSerializer(EdgeSerializer):
    evidence = EdgeEvidenceSerializer(many=True, read_only=True)
    ads = serializers.SerializerMethodField()

    class Meta(EdgeSerializer.Meta):
        fields = [*EdgeSerializer.Meta.fields, "verdict_note", "verdict_reason", "verdict_at", "ads", "evidence"]

    def get_ads(self, obj) -> list[dict]:
        return AdListSerializer([obj.ad_a, obj.ad_b], many=True).data


class VerdictSerializer(serializers.Serializer):
    verdict = serializers.ChoiceField(choices=[Edge.Verdict.CONFIRMED, Edge.Verdict.REJECTED, Edge.Verdict.UNSURE])
    # Bez powodu decyzja zapisuje się z powodem "nieznany", żeby stary klient dalej działał.
    reason = serializers.ChoiceField(choices=[c for c, _ in EdgeDecision.Reason.choices if c != EdgeDecision.Reason.UNKNOWN], required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=4000)


class SimulationSerializer(serializers.Serializer):
    exclude = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=True, max_length=500)
    edge_version = serializers.CharField(required=False, allow_blank=True)


class CampaignSerializer(serializers.ModelSerializer):
    key = serializers.CharField(read_only=True)
    size = serializers.IntegerField(read_only=True)

    class Meta:
        model = Campaign
        fields = ["id", "key", "label", "size", "created_at"]


class OperatorSerializer(serializers.ModelSerializer):
    key = serializers.CharField(read_only=True)
    size = serializers.IntegerField(read_only=True)

    class Meta:
        model = Operator
        fields = ["id", "key", "label", "size", "created_at"]
