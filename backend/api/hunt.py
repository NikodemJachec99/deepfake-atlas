"""Łowca domen w API: lista kandydatów, profil operatora, start przebiegu i zgłoszenie domeny do analizy."""

from django.db.models import Case, IntegerField, Value, When
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response

from hunting import service
from hunting.models import HuntCandidate, HuntRun
from hunting.profile import build_profile
from similarity.models import Operator

from .serializers import AnalysisSerializer
from .views import AnalysesThrottle, get_object_or_404

MAX_DAYS = 90
MAX_QUERIES = 40
MAX_CRAWL = 100


class HuntCandidateSerializer(serializers.ModelSerializer):
    operator = serializers.CharField(source="operator.key", read_only=True)
    operator_id = serializers.IntegerField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    cert = serializers.SerializerMethodField()
    ad = serializers.SerializerMethodField()
    alert = serializers.SerializerMethodField()

    class Meta:
        model = HuntCandidate
        fields = [
            "id", "domain", "operator", "operator_id", "sources", "status", "status_label", "prelim_score", "score_parts", "cert",
            "bits", "probability", "evidence", "note", "final_url", "http_status", "crawl_error", "html_sha", "screenshot_sha",
            "attempts", "checked_at", "analysis", "ad", "alert", "run", "created_at", "updated_at",
        ]

    def get_cert(self, obj) -> dict | None:
        if not obj.cert_not_before and not obj.cert_issuer:
            return None
        return {"issuer": obj.cert_issuer, "serial": obj.cert_serial, "not_before": obj.cert_not_before, "crtsh_id": obj.crtsh_id}

    def get_ad(self, obj) -> int | None:
        return obj.analysis.ad_id if obj.analysis_id else None

    def get_alert(self, obj) -> int | None:
        alert = obj.alerts.first()
        return alert.pk if alert else None


class HuntRunSerializer(serializers.ModelSerializer):
    operator = serializers.SerializerMethodField()

    class Meta:
        model = HuntRun
        fields = ["id", "operator", "params", "status", "stats", "error", "created_at", "started_at", "finished_at"]

    def get_operator(self, obj) -> str | None:
        return obj.operator.key if obj.operator_id else None


class HuntRunRequestSerializer(serializers.Serializer):
    operator = serializers.IntegerField(required=False, allow_null=True)
    days = serializers.IntegerField(required=False, min_value=1, max_value=MAX_DAYS, default=service.DEFAULTS["days"])
    max_queries = serializers.IntegerField(required=False, min_value=1, max_value=MAX_QUERIES, default=service.DEFAULTS["max_queries"])
    max_crawl = serializers.IntegerField(required=False, min_value=0, max_value=MAX_CRAWL, default=service.DEFAULTS["max_crawl"])
    crawl = serializers.BooleanField(required=False, default=service.DEFAULTS["crawl"])

    def validate_operator(self, value):
        if value is not None and not Operator.objects.filter(pk=value, merged_into__isnull=True, memberships__isnull=False).exists():
            raise serializers.ValidationError("Nie ma takiego operatora.")
        return value


def _operator_pk(value: str) -> int | None:
    """Identyfikator albo klucz operatora (`7` albo `O-0007`)."""
    raw = value.upper().removeprefix("O-")
    return int(raw) if raw.isdigit() else None


class HuntList(generics.ListAPIView):
    """Kandydaci łowcy domen. Potwierdzeni pierwsi, potem po wyniku wstępnym.
    Filtry: `?operator=<id albo O-0007>`, `?status=candidate|confirmed|rejected|unavailable` (po przecinku kilka),
    `?source=crtsh|cert_pl`."""

    serializer_class = HuntCandidateSerializer

    def get_queryset(self):
        queryset = HuntCandidate.objects.select_related("operator", "analysis")
        params = self.request.query_params
        if operator := params.get("operator"):
            queryset = queryset.filter(operator_id=_operator_pk(operator) or 0)
        if statuses := params.get("status"):
            queryset = queryset.filter(status__in=statuses.split(","))
        if source := params.get("source"):
            queryset = queryset.filter(sources__contains=[source])
        rank = Case(
            When(status=HuntCandidate.Status.CONFIRMED, then=Value(0)),
            When(status=HuntCandidate.Status.CANDIDATE, then=Value(1)),
            When(status=HuntCandidate.Status.UNAVAILABLE, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
        return queryset.annotate(rank=rank).order_by("rank", "-prelim_score", "-created_at", "-id")


@extend_schema(responses=dict)
@api_view(["GET"])
def operator_hunt_profile(request, pk):
    """Wzorce, po których łowca szuka nowych domen operatora, każdy z reklamami, z których go wzięto."""
    operator = get_object_or_404(Operator.objects.filter(merged_into__isnull=True), pk=pk)
    profile = build_profile(operator).to_dict()
    counts: dict[str, int] = {}
    for value in operator.hunt_candidates.values_list("status", flat=True):
        counts[value] = counts.get(value, 0) + 1
    profile["candidates"] = counts
    return Response(profile)


@extend_schema(request=HuntRunRequestSerializer, responses={202: HuntRunSerializer})
@api_view(["POST"])
@throttle_classes([AnalysesThrottle])
def hunt_run(request):
    """Uruchamia przebieg łowcy w tle (ANALYSIS_RUNNER). Odpowiedź ma identyfikator do `GET /api/hunt/runs/{id}`.
    Gdy poprzedni przebieg jeszcze trwa (do dwóch godzin), odpowiada 409 z jego danymi."""
    from workflows import runner

    payload = HuntRunRequestSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    if (busy := service.active_run()) is not None:
        return Response({"detail": "Poprzedni przebieg łowcy jeszcze trwa.", "run": HuntRunSerializer(busy).data}, status=status.HTTP_409_CONFLICT)
    params = dict(payload.validated_data)
    run = service.create_run(params, params.get("operator"))
    runner.start_hunt(str(run.pk))
    run.refresh_from_db()
    return Response(HuntRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class HuntRunList(generics.ListAPIView):
    serializer_class = HuntRunSerializer
    queryset = HuntRun.objects.select_related("operator")


@extend_schema(responses=HuntRunSerializer)
@api_view(["GET"])
def hunt_run_detail(request, pk):
    return Response(HuntRunSerializer(get_object_or_404(HuntRun.objects.select_related("operator"), pk=pk)).data)


@extend_schema(request=None, responses={201: AnalysisSerializer})
@api_view(["POST"])
@throttle_classes([AnalysesThrottle])
def hunt_analyze(request, pk):
    """Zgłasza domenę kandydata do pełnej analizy (ten potok co `POST /api/analyses`). Drugie zgłoszenie tej samej
    domeny zwraca 409 z istniejącą analizą."""
    candidate = get_object_or_404(HuntCandidate.objects.select_related("operator", "analysis"), pk=pk)
    if candidate.analysis_id:
        body = {"detail": "Domena jest już zgłoszona do analizy.", "analysis": AnalysisSerializer(candidate.analysis).data}
        return Response(body, status=status.HTTP_409_CONFLICT)
    analysis = service.submit_for_analysis(candidate)
    return Response(AnalysisSerializer(analysis).data, status=status.HTTP_201_CREATED)
