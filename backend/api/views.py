import asyncio
import json
import tempfile
import uuid
import zipfile
from pathlib import Path

from asgiref.sync import sync_to_async
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from ads.models import Ad, Analysis
from collectors import bundle
from evidence import store
from evidence.kinds import BAND_KINDS, FAMILIES, KINDS
from evidence.models import AdMarker, Artifact, AuditLog
from extractors.url import redact_url
from similarity import simulation, suggestions, timeline
from similarity.models import Campaign, Edge, Operator
from similarity.service import assign_campaign, assign_operator
from workflows import runner

from . import serializers as s

MAX_ZIP_BYTES = 2 * 1024**3
MAX_ZIP_FILES = 5000
AD_RELATED = ("membership__campaign", "operator_membership__operator")


@extend_schema(request=s.AnalysisCreateSerializer, responses={201: s.AnalysisSerializer})
@api_view(["POST"])
def analysis_create(request):
    """Tryb Discovery: przyjmuje URL albo tekst i uruchamia analizę. Postęp idzie strumieniem `events_url`."""
    payload = s.AnalysisCreateSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    kind, value = payload.validated_data["kind"], payload.validated_data["value"]
    # Tokeny dostępu doklejone do adresu zamieniamy na skrót, zanim cokolwiek trafi do bazy.
    analysis = Analysis.objects.create(input_kind=kind, input_value=redact_url(value) if kind == Analysis.Kind.URL else value)
    runner.start(str(analysis.pk))
    analysis.refresh_from_db()
    return Response(s.AnalysisSerializer(analysis).data, status=status.HTTP_201_CREATED)


def _safe_extract(upload, target: Path) -> None:
    """Rozpakowuje archiwum tylko do katalogu docelowego i z limitem rozmiaru."""
    with zipfile.ZipFile(upload) as archive:
        members = archive.infolist()
        if len(members) > MAX_ZIP_FILES or sum(m.file_size for m in members) > MAX_ZIP_BYTES:
            raise ValueError("Archiwum jest za duże")
        root = target.resolve()
        for member in members:
            destination = (target / member.filename).resolve()
            if root != destination and root not in destination.parents:
                raise ValueError("Archiwum zawiera ścieżkę poza katalogiem docelowym")
        archive.extractall(target)


@extend_schema(
    request={"multipart/form-data": {"type": "object", "properties": {"files": {"type": "array", "items": {"type": "string", "format": "binary"}}}}},
    responses={201: s.AnalysisSerializer(many=True)},
)
@api_view(["POST"])
@parser_classes([MultiPartParser])
def analysis_upload(request):
    """Tryb Discovery dla plików: zrzut ekranu reklamy, zapisana strona, HAR albo ZIP z całą sprawą.

    Pliki przesłane razem traktujemy jako jedną sprawę. ZIP może zawierać wiele spraw w podkatalogach.
    """
    files = request.FILES.getlist("files")
    if not files:
        return Response({"files": "Prześlij co najmniej jeden plik"}, status=status.HTTP_400_BAD_REQUEST)
    name = f"upload-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory(prefix="scamdna-upload-") as tmp:
        case_root = Path(tmp) / "sprawa"
        case_root.mkdir()
        try:
            for upload in files:
                filename = Path(upload.name).name
                if filename.lower().endswith(".zip"):
                    _safe_extract(upload, case_root)
                else:
                    (case_root / filename).write_bytes(upload.read())
        except (ValueError, zipfile.BadZipFile) as exc:
            return Response({"files": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        directories = bundle.case_dirs(case_root)
        analyses = []
        for directory in directories:
            analyses += bundle.import_case(directory, bundle=name, case=directory.name if len(directories) > 1 else "1")
    if not analyses:
        return Response({"files": "Nie rozpoznano żadnego materiału (HTML, HAR, obraz, wideo)"}, status=status.HTTP_400_BAD_REQUEST)
    for analysis in analyses:
        runner.start(str(analysis.pk))
        analysis.refresh_from_db()
    return Response(s.AnalysisSerializer(analyses, many=True).data, status=status.HTTP_201_CREATED)


class AnalysisDetail(generics.RetrieveAPIView):
    queryset = Analysis.objects.all()
    serializer_class = s.AnalysisSerializer


def _events_after(analysis_id, seq: int) -> tuple[list[dict], str]:
    analysis = Analysis.objects.get(pk=analysis_id)
    events = s.AnalysisEventSerializer(analysis.events.filter(seq__gt=seq), many=True).data
    return list(events), analysis.status


async def analysis_events(request, pk):
    """Strumień SSE zdarzeń analizy. Zaczyna od `?after=` (domyślnie 0) i kończy się razem z analizą."""
    if not await Analysis.objects.filter(pk=pk).aexists():
        raise Http404
    after = int(request.GET.get("after", 0))

    async def stream():
        seq = after
        while True:
            events, state = await sync_to_async(_events_after)(pk, seq)
            for event in events:
                seq = event["seq"]
                yield f"id: {seq}\nevent: {event['stage']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            if state in (Analysis.Status.DONE, Analysis.Status.FAILED) and not events:
                yield "event: close\ndata: {}\n\n"
                return
            await asyncio.sleep(0.4)

    response = StreamingHttpResponse(stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class AdList(generics.ListAPIView):
    serializer_class = s.AdListSerializer

    def get_queryset(self):
        queryset = Ad.objects.select_related(*AD_RELATED).order_by("-id")
        params = self.request.query_params
        if source := params.get("source"):
            queryset = queryset.filter(source=source)
        if campaign := params.get("campaign"):
            queryset = queryset.filter(membership__campaign_id=campaign)
        if operator := params.get("operator"):
            queryset = queryset.filter(operator_membership__operator_id=operator)
        if case := params.get("case"):
            queryset = queryset.filter(labels__case=case)
        if query := params.get("q"):
            queryset = queryset.filter(Q(title__icontains=query) | Q(text__icontains=query) | Q(landing_url__icontains=query))
        return queryset


class AdDetail(generics.RetrieveAPIView):
    queryset = Ad.objects.select_related("advertiser", *AD_RELATED)
    serializer_class = s.AdDetailSerializer


class AdEdges(generics.ListAPIView):
    serializer_class = s.EdgeSerializer
    pagination_class = None

    def get_queryset(self):
        pk = self.kwargs["pk"]
        return Edge.objects.filter(Q(ad_a_id=pk) | Q(ad_b_id=pk)).order_by("-probability")


class EdgeDetail(generics.RetrieveAPIView):
    """Panel dowodów: z czego wynika połączenie dwóch reklam."""

    queryset = Edge.objects.select_related("ad_a", "ad_b").prefetch_related("evidence")
    serializer_class = s.EdgeDetailSerializer


@extend_schema(request=s.VerdictSerializer, responses=s.EdgeDetailSerializer)
@api_view(["POST"])
def edge_verdict(request, pk):
    """Decyzja analityka. Odrzucona krawędź przestaje spinać kampanię, a decyzja trafia do dziennika audytu."""
    edge = get_object_or_404(Edge, pk=pk)
    payload = s.VerdictSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    user = request.user if request.user.is_authenticated else None
    edge.verdict = payload.validated_data["verdict"]
    edge.verdict_note = payload.validated_data.get("note", "")
    edge.verdict_by = user
    edge.verdict_at = timezone.now()
    edge.save()
    AuditLog.objects.create(
        user=user, action="edge.verdict", object_type="edge", object_id=str(edge.pk),
        payload={"verdict": edge.verdict, "note": edge.verdict_note},
    )
    return Response(s.EdgeDetailSerializer(edge).data)


@extend_schema(request=s.SimulationSerializer, responses=dict)
@api_view(["POST"])
def edge_simulate(request, pk):
    """Laboratorium dowodów: przeliczenie krawędzi bez wybranych dowodów. Niczego nie zapisuje."""
    edge = get_object_or_404(Edge, pk=pk)
    payload = s.SimulationSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    try:
        result = simulation.simulate(edge, payload.validated_data["exclude"], payload.validated_data.get("edge_version") or None)
    except simulation.SimulationError as exc:
        return Response({"detail": str(exc), **exc.extra}, status=exc.status)
    return Response(result)


@extend_schema(responses=dict)
@api_view(["GET"])
def edge_suggestions(request, pk):
    """Co sprawdzić dalej: wskazówki z brakujących dowodów tej pary. Bez zapytań na zewnątrz."""
    edge = get_object_or_404(Edge.objects.select_related("ad_a", "ad_b"), pk=pk)
    return Response(suggestions.suggestions_for(edge))


def _group_detail(group, serializer, relations: list[str]) -> dict:
    """Wspólny kształt karty kampanii i operatora: reklamy, krawędzie i markery, które grupę spinają."""
    ad_ids = list(group.memberships.values_list("ad_id", flat=True))
    ads = Ad.objects.filter(pk__in=ad_ids).select_related(*AD_RELATED).order_by("first_seen", "id")
    edges = Edge.objects.filter(ad_a_id__in=ad_ids, ad_b_id__in=ad_ids, relation__in=relations)
    core = (
        AdMarker.objects.filter(ad_id__in=ad_ids)
        .exclude(marker__kind__in=BAND_KINDS)
        .values("marker__kind", "marker__value", "marker__ad_count")
        .annotate(in_group=Count("ad_id"))
        .filter(in_group__gte=2)
        .order_by("-in_group")[:80]
    )
    return {
        **serializer(group).data,
        "ads": s.AdListSerializer(ads, many=True).data,
        "edges": s.EdgeSerializer(edges, many=True).data,
        "core_markers": [
            {
                "kind": row["marker__kind"],
                "label": KINDS[row["marker__kind"]].label,
                "family": KINDS[row["marker__kind"]].family,
                "decisive": KINDS[row["marker__kind"]].decisive,
                "value": row["marker__value"],
                "in_group": row["in_group"],
                "ad_count": row["marker__ad_count"],
            }
            for row in core
        ],
    }


class CampaignList(generics.ListAPIView):
    serializer_class = s.CampaignSerializer

    def get_queryset(self):
        return Campaign.objects.filter(merged_into__isnull=True).annotate(size=Count("memberships")).filter(size__gt=0).order_by("-size", "id")


@api_view(["GET"])
def campaign_detail(request, pk):
    """Kampania: reklamy z tą samą opowieścią i wspólnym źródłem, krawędzie i markery rdzeniowe."""
    campaign = get_object_or_404(Campaign.objects.annotate(size=Count("memberships")), pk=pk)
    return Response(_group_detail(campaign, s.CampaignSerializer, [Edge.Relation.SAME_CAMPAIGN]))


class OperatorList(generics.ListAPIView):
    serializer_class = s.OperatorSerializer

    def get_queryset(self):
        return Operator.objects.filter(merged_into__isnull=True).annotate(size=Count("memberships")).filter(size__gt=0).order_by("-size", "id")


@api_view(["GET"])
def operator_detail(request, pk):
    """Operator: wspólne zaplecze kilku kampanii. Markery rdzeniowe to jego odcisk."""
    operator = get_object_or_404(Operator.objects.annotate(size=Count("memberships")), pk=pk)
    detail = _group_detail(operator, s.OperatorSerializer, [Edge.Relation.SAME_CAMPAIGN, Edge.Relation.SAME_OPERATOR])
    detail["campaigns"] = sorted({ad["campaign"] for ad in detail["ads"] if ad["campaign"]})
    return Response(detail)


def _timeline(group, relations: list[str]) -> dict:
    ad_ids = list(group.memberships.values_list("ad_id", flat=True))
    return {"group": group.key, **timeline.build(ad_ids, relations)}


@api_view(["GET"])
def campaign_timeline(request, pk):
    """Oś obserwacji kampanii: reklamy, ślady, powiązania, domeny, certyfikaty, wpisy CERT Polska. Każde zdarzenie z rodzajem czasu i źródłem."""
    return Response(_timeline(get_object_or_404(Campaign, pk=pk), [Edge.Relation.SAME_CAMPAIGN]))


@api_view(["GET"])
def operator_timeline(request, pk):
    """Oś obserwacji operatora, w tym samym kształcie co oś kampanii."""
    return Response(_timeline(get_object_or_404(Operator, pk=pk), [Edge.Relation.SAME_CAMPAIGN, Edge.Relation.SAME_OPERATOR]))


@api_view(["GET"])
def graph(request):
    """Graf dla Sigma.js. Filtry: `?campaign=ID`, `?operator=ID`, `?ad=ID` (reklama z sąsiadami). Bez filtra wszystkie krawędzie do limitu."""
    params = request.query_params
    edges = Edge.objects.all()
    focus: set[int] = set()
    if campaign := params.get("campaign"):
        focus = set(get_object_or_404(Campaign, pk=campaign).memberships.values_list("ad_id", flat=True))
    elif operator := params.get("operator"):
        focus = set(get_object_or_404(Operator, pk=operator).memberships.values_list("ad_id", flat=True))
    elif ad := params.get("ad"):
        focus = {int(ad)}
    if focus:
        edges = edges.filter(Q(ad_a_id__in=focus) | Q(ad_b_id__in=focus))
    if relation := params.get("relation"):
        edges = edges.filter(relation__in=relation.split(","))
    edges = list(edges.order_by("-probability")[: int(params.get("limit", 2000))])
    node_ids = {e.ad_a_id for e in edges} | {e.ad_b_id for e in edges} | focus
    nodes = Ad.objects.filter(pk__in=node_ids).select_related(*AD_RELATED)
    return Response(
        {
            "nodes": [
                {
                    "id": n.pk,
                    "label": n.title or n.landing_url or f"Reklama {n.pk}",
                    "source": n.source,
                    "campaign": n.membership.campaign.key if hasattr(n, "membership") else None,
                    "operator": n.operator_membership.operator.key if hasattr(n, "operator_membership") else None,
                    "case": n.labels.get("case"),
                    "listed": "cert_pl" in n.labels,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": e.pk,
                    "source": e.ad_a_id,
                    "target": e.ad_b_id,
                    "relation": e.relation,
                    "duplicate": e.duplicate,
                    "probability": e.probability,
                    "bits": e.bits,
                    "family": max(e.families, key=e.families.get) if e.families else None,
                    "families": e.families,
                    "verdict": e.verdict,
                }
                for e in edges
            ],
        }
    )


@api_view(["GET"])
def kinds(request):
    """Słownik rodzin i typów markerów, żeby interfejs nie trzymał własnej kopii."""
    return Response(
        {
            "families": [{"code": code, "label": label} for code, label in FAMILIES.items()],
            "kinds": [
                {"code": k.code, "family": k.family, "label": k.label, "decisive": k.decisive, "soft": k.soft}
                for k in KINDS.values()
                if k.code not in BAND_KINDS
            ],
        }
    )


@api_view(["GET"])
def stats(request):
    """Liczby do paska stanu: wielkość korpusu i tego, co silnik w nim znalazł."""
    return Response(
        {
            "ads": Ad.objects.count(),
            "campaigns": Campaign.objects.filter(merged_into__isnull=True, memberships__isnull=False).distinct().count(),
            "operators": Operator.objects.filter(merged_into__isnull=True, memberships__isnull=False).distinct().count(),
            "edges": dict(Edge.objects.values_list("relation").annotate(n=Count("id"))),
            "by_source": dict(Ad.objects.values_list("source").annotate(n=Count("id"))),
            "cert_pl_listed": Ad.objects.filter(labels__has_key="cert_pl").count(),
            "last_analysis": Analysis.objects.order_by("-created_at").values_list("created_at", flat=True).first(),
        }
    )


def artifact(request, sha256):
    """Surowy dowód. Zawsze jako załącznik tekstowy: to bywa złośliwy HTML i nie może się wyrenderować."""
    item = get_object_or_404(Artifact, pk=sha256)
    content_type = "text/plain; charset=utf-8" if item.kind.startswith(("html", "har")) else "application/octet-stream"
    response = HttpResponse(store.get(item.sha256), content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{item.sha256[:16]}.{item.kind}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


IMAGE_SIGNATURES = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"RIFF": "image/webp", b"GIF8": "image/gif"}


def artifact_image(request, sha256):
    """Zrzut reklamy do wyświetlenia. Tylko artefakty obrazów i tylko, gdy bajty faktycznie są obrazem."""
    item = get_object_or_404(Artifact, pk=sha256, kind="creative_image")
    data = store.get(item.sha256)
    content_type = next((mime for magic, mime in IMAGE_SIGNATURES.items() if data.startswith(magic)), None)
    if content_type is None:
        raise Http404
    response = HttpResponse(data, content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@api_view(["POST"])
def ad_recluster(request, pk):
    """Ponownie przypisuje reklamę do kampanii i operatora, np. po odrzuceniu krawędzi."""
    ad = get_object_or_404(Ad, pk=pk)
    return Response({**assign_campaign(ad), **assign_operator(ad)})
