import asyncio
import io
import json
import re
import tempfile
import uuid
import zipfile
from pathlib import Path

from asgiref.sync import sync_to_async
from django.core.management import call_command
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.decorators import api_view, parser_classes, throttle_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from ads.models import Ad, Analysis
from collectors import bundle
from evidence import store
from evidence.kinds import BAND_KINDS, FAMILIES, KINDS
from evidence.models import AdMarker, Artifact, AuditLog
from extractors import video
from extractors.url import redact_url
from people.display import display_value, person_names
from similarity import assist_view, decisions, observations, package, precedents, simulation, stix, suggestions, timeline, weakest
from similarity.models import Alert, Campaign, CampaignMembership, Edge, EdgeDecision, Operator, OperatorMembership
from similarity.service import assign_campaign, assign_operator
from workflows import runner

from . import serializers as s

MAX_ZIP_BYTES = 2 * 1024**3
MAX_ZIP_FILES = 5000
class AnalysesThrottle(UserRateThrottle):
    """Limit nowych analiz na klienta (adres IP bez logowania). Każda analiza to pobieranie stron i wzbogacanie."""

    scope = "analyses"


AD_RELATED = ("membership__campaign", "operator_membership__operator")


@extend_schema(request=s.AnalysisCreateSerializer, responses={201: s.AnalysisSerializer})
@api_view(["POST"])
@throttle_classes([AnalysesThrottle])
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
@throttle_classes([AnalysesThrottle])
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
                filename = Path(upload.name or "").name
                if filename in ("", ".", "..") or filename.startswith("."):
                    raise ValueError("Niedozwolona nazwa pliku")
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
    """Decyzja analityka z powodem. Zapisuje migawkę dowodów do historii decyzji i dziennika audytu.
    Odrzucona krawędź przestaje spinać kampanię. Wagi, dowody i relacja zostają bez zmian."""
    edge = get_object_or_404(Edge, pk=pk)
    payload = s.VerdictSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    user = request.user if request.user.is_authenticated else None
    data = payload.validated_data
    decisions.decide(edge.pk, data["verdict"], data.get("reason") or EdgeDecision.Reason.UNKNOWN, data.get("note", ""), user)
    edge.refresh_from_db()
    return Response(s.EdgeDetailSerializer(edge).data)


@extend_schema(responses=dict)
@api_view(["GET"])
def edge_assist(request, pk):
    """Sugestia Jev dla krawędzi: stan adaptera i ostatnia zapisana sugestia. Nie wywołuje Jev i nic nie zapisuje."""
    return Response(assist_view.build(get_object_or_404(Edge, pk=pk)))


@extend_schema(responses=dict)
@api_view(["GET"])
def edge_precedents(request, pk):
    """Podobne wcześniejsze rozstrzygnięcia innych par. Doradczo, bez zmian krawędzi, wag i grup."""
    edge = get_object_or_404(Edge, pk=pk)
    try:
        limit = int(request.query_params.get("limit", precedents.DEFAULT_LIMIT))
    except ValueError:
        return Response({"detail": "limit musi być liczbą"}, status=status.HTTP_400_BAD_REQUEST)
    return Response(precedents.find(edge, limit))


@extend_schema(responses=dict)
@api_view(["GET"])
def edge_decisions(request, pk):
    """Historia decyzji o krawędzi, od najnowszej, z migawką podstawy każdej decyzji."""
    edge = get_object_or_404(Edge, pk=pk)
    rows = EdgeDecision.objects.filter(edge=edge).select_related("user")
    return Response({"edge": edge.pk, "current": edge.verdict, "decisions": [decisions.serialize(d) for d in rows]})


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


@extend_schema(request=s.WeakestLinkSerializer, responses=dict)
@api_view(["POST"])
def edge_weakest_link(request, pk):
    """Test najsłabszego ogniwa: najmniejsze zestawy grup śladów, których utrata zmienia relację. Niczego nie zapisuje."""
    edge = get_object_or_404(Edge, pk=pk)
    payload = s.WeakestLinkSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    data = payload.validated_data
    try:
        result = weakest.weakest_link(
            edge, data["max_group_size"], data["max_scenarios"], data["time_limit_ms"], data.get("edge_version") or None
        )
    except simulation.SimulationError as exc:
        return Response({"detail": str(exc), **exc.extra}, status=exc.status)
    return Response(result)


@api_view(["GET"])
def ad_observations(request, pk):
    """Obserwacja strony tej reklamy i strony, z którymi da się ją porównać (ten sam adres albo ta sama domena w sprawie)."""
    ad = get_object_or_404(Ad, pk=pk)
    found = observations.candidates(ad)
    own = observations.observation(ad)
    message = ""
    if not own:
        message = "Ta reklama nie ma zapisu obserwacji: materiał bez strony albo import sprzed tej funkcji."
    elif not found:
        message = "Brak innych przechwyceń tego samego adresu ani tej samej domeny w tej sprawie."
    return Response({"ad": ad.pk, "observation": observations.side(ad, own), "artifacts": observations.artifacts(ad), "candidates": found, "message": message})


@api_view(["GET"])
def observations_compare(request):
    """Porównanie dwóch obserwacji stron: `?a=ID&b=ID`. Tylko do odczytu, bez sieci."""
    try:
        a_id, b_id = int(request.query_params["a"]), int(request.query_params["b"])
    except (KeyError, ValueError):
        return Response({"detail": "Podaj dwa identyfikatory reklam: ?a=ID&b=ID."}, status=400)
    if a_id == b_id:
        return Response({"detail": "Porównanie wymaga dwóch różnych reklam."}, status=400)
    a, b = get_object_or_404(Ad, pk=a_id), get_object_or_404(Ad, pk=b_id)
    return Response(observations.compare_with_links(a, b))


@api_view(["GET"])
def export_corpus(request):
    """Wzbogacony korpus jako ZIP: reklamy z markerami, krawędzie z dowodami, grupy, opis. `?source=capture` zawęża do materiałów spraw."""
    source = request.query_params.get("source") or None
    if source and source not in {choice for choice, _label in Ad._meta.get_field("source").choices}:
        return Response({"detail": f"Nieznane źródło: {source}"}, status=400)
    with tempfile.TemporaryDirectory(prefix="scamdna-eksport-") as tmp:
        folder = Path(tmp) / "korpus"
        call_command("export_corpus", str(folder), **({"source": source} if source else {}))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(folder.iterdir()):
                archive.write(item, f"korpus/{item.name}")
    name = f"scamdna-korpus-{source or 'wszystko'}-{timezone.now():%Y%m%d-%H%M}.zip"
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


@api_view(["GET"])
def export_stix(request):
    """Operatorzy i kampanie jako bundle STIX 2.1 (`?operator=ID`, `?campaign=ID`). Tylko grupy z materiałów zgłoszonych jako podejrzane."""
    params = {}
    for name in ("operator", "campaign"):
        raw = request.query_params.get(name)
        if raw:
            if not raw.isdigit():
                return Response({"detail": f"{name} musi być liczbą"}, status=400)
            params[f"{name}_id"] = int(raw)
    data = stix.bundle(**params)
    response = HttpResponse(json.dumps(data, ensure_ascii=False, indent=1), content_type="application/stix+json;version=2.1")
    response["Content-Disposition"] = f'attachment; filename="scamdna-stix-{timezone.now():%Y%m%d-%H%M}.json"'
    return response


def _package_response(request, kind: str, model, pk: int):
    group = get_object_or_404(model, pk=pk)
    raw = request.query_params.get("surowe", "1")
    if raw not in ("0", "1"):
        return Response({"detail": "surowe musi być 0 albo 1"}, status=400)
    try:
        built = package.build(kind, group, include_raw=raw == "1")
    except package.GroupNotFound:
        return Response({"detail": f"{group.key} nie ma żadnej reklamy, więc nie ma z czego zrobić pakietu"}, status=404)
    AuditLog.objects.create(
        action="package", object_type=kind, object_id=group.key,
        payload={"file": built.filename, "files": built.files, "bytes": built.size, "skipped": built.skipped, "raw": raw == "1"},
    )
    return FileResponse(built.file, as_attachment=True, filename=built.filename, content_type="application/zip")


@extend_schema(responses={(200, "application/zip"): OpenApiTypes.BINARY})
@api_view(["GET"])
def operator_package(request, pk):
    """Pakiet dowodowy operatora jako ZIP: raport do druku, artefakty z manifestem SHA-256, STIX, krawędzie, skrypt weryfikacji. `?surowe=0` pomija HAR i HTML."""
    return _package_response(request, "operator", Operator, pk)


@extend_schema(responses={(200, "application/zip"): OpenApiTypes.BINARY})
@api_view(["GET"])
def campaign_package(request, pk):
    """Pakiet dowodowy kampanii, ta sama zawartość co dla operatora. `?surowe=0` pomija HAR i HTML."""
    return _package_response(request, "campaign", Campaign, pk)


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
    names = person_names()
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
                "display_value": display_value(row["marker__kind"], row["marker__value"], names),
                "in_group": row["in_group"],
                "ad_count": row["marker__ad_count"],
            }
            for row in core
        ],
    }


def _group_stats(membership_model, field: str, group_ids) -> dict[int, dict]:
    """Skład grup: reklamy według źródła, liczba spraw i reklam z domeną na Liście Ostrzeżeń CERT Polska."""
    stats: dict[int, dict] = {gid: {"sources": {}, "cases": 0, "cert_pl": 0} for gid in group_ids}
    rows = membership_model.objects.filter(**{f"{field}_id__in": group_ids}).values(f"{field}_id", "ad__source").annotate(n=Count("id"))
    for row in rows:
        stats[row[f"{field}_id"]]["sources"][row["ad__source"]] = row["n"]
    cases = (membership_model.objects.filter(**{f"{field}_id__in": group_ids}, ad__labels__has_key="case")
             .values(f"{field}_id").annotate(n=Count("ad__labels__case", distinct=True)))
    for row in cases:
        stats[row[f"{field}_id"]]["cases"] = row["n"]
    listed = (membership_model.objects.filter(**{f"{field}_id__in": group_ids}, ad__labels__has_key="cert_pl")
              .values(f"{field}_id").annotate(n=Count("id")))
    for row in listed:
        stats[row[f"{field}_id"]]["cert_pl"] = row["n"]
    return stats


class _GroupList(generics.ListAPIView):
    """Lista grup od największej. `?source=capture` zostawia grupy, w których jest reklama z tego źródła."""

    model = None
    membership = None
    field = ""

    def get_queryset(self):
        queryset = self.model.objects.filter(merged_into__isnull=True)
        if source := self.request.query_params.get("source"):
            # Podzapytanie, a nie filtr po tym samym złączeniu: rozmiar grupy ma liczyć wszystkie reklamy.
            with_source = self.membership.objects.filter(ad__source__in=source.split(",")).values(f"{self.field}_id")
            queryset = queryset.filter(pk__in=with_source)
        return queryset.annotate(size=Count("memberships")).filter(size__gt=0).order_by("-size", "id")

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        items = page if page is not None else list(self.get_queryset())
        stats = _group_stats(self.membership, self.field, [g.pk for g in items])
        data = [{**self.get_serializer(g).data, **stats[g.pk]} for g in items]
        return self.get_paginated_response(data) if page is not None else Response(data)


class CampaignList(_GroupList):
    serializer_class = s.CampaignSerializer
    model, membership, field = Campaign, CampaignMembership, "campaign"


@api_view(["GET"])
def campaign_detail(request, pk):
    """Kampania: reklamy z tą samą opowieścią i wspólnym źródłem, krawędzie i markery rdzeniowe."""
    campaign = get_object_or_404(Campaign.objects.annotate(size=Count("memberships")), pk=pk)
    return Response(_group_detail(campaign, s.CampaignSerializer, [Edge.Relation.SAME_CAMPAIGN]))


class OperatorList(_GroupList):
    serializer_class = s.OperatorSerializer
    model, membership, field = Operator, OperatorMembership, "operator"


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
            "verdict_reasons": decisions.reasons(),
        }
    )


@api_view(["GET"])
def weights(request):
    """Wagi eksperckie i uczone (EM) dla każdego typu markera, żeby widok pokazał, co się zmienia."""
    from similarity import learning

    return Response(learning.weights_overview())


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
            "alerts_unseen": Alert.objects.filter(seen=False).count(),
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
    item = get_object_or_404(Artifact, pk=sha256, kind__in=("creative_image", "video_frame", "page_screenshot"))
    data = store.get(item.sha256)
    content_type = next((mime for magic, mime in IMAGE_SIGNATURES.items() if data.startswith(magic)), None)
    if content_type is None:
        raise Http404
    response = HttpResponse(data, content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def artifact_video(request, sha256):
    """Nagranie reklamy albo ekranu do odtworzenia w <video>. Tylko artefakty nagrań i tylko, gdy bajty to MP4,
    MOV albo WebM. Obsługuje pojedynczy zakres bajtów, żeby odtwarzacz mógł przewijać."""
    item = get_object_or_404(Artifact, pk=sha256, kind="creative_video")
    data = store.get(item.sha256)
    mime = video.content_type(data[:16])
    if mime is None:
        raise Http404
    total = len(data)
    start, end, status_code = 0, total - 1, 200
    match = _RANGE.match(request.headers.get("Range", "").strip())
    if match and (match.group(1) or match.group(2)):
        if match.group(1):
            start = int(match.group(1))
            end = min(int(match.group(2)), total - 1) if match.group(2) else total - 1
        else:
            start = max(0, total - int(match.group(2)))
        if start > end or start >= total:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{total}"
            return response
        status_code = 206
    response = HttpResponse(data[start : end + 1], content_type=mime, status=status_code)
    if status_code == 206:
        response["Content-Range"] = f"bytes {start}-{end}/{total}"
    response["Accept-Ranges"] = "bytes"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@api_view(["POST"])
def ad_recluster(request, pk):
    """Ponownie przypisuje reklamę do kampanii i operatora, np. po odrzuceniu krawędzi."""
    ad = get_object_or_404(Ad, pk=pk)
    return Response({**assign_campaign(ad), **assign_operator(ad)})


class AlertList(generics.ListAPIView):
    """Nowe materiały powiązane z wcześniej wykrytymi kampaniami i operatorami, najnowsze pierwsze.
    `?unseen=1` zostawia nieprzejrzane."""

    serializer_class = s.AlertSerializer

    def get_queryset(self):
        queryset = Alert.objects.select_related("ad", "campaign", "operator")
        if self.request.query_params.get("unseen") in ("1", "true"):
            queryset = queryset.filter(seen=False)
        return queryset


@api_view(["POST"])
def alert_seen(request, pk):
    """Oznacza alert jako przejrzany. Ciało `{"seen": false}` cofa oznaczenie."""
    alert = get_object_or_404(Alert.objects.select_related("ad", "campaign", "operator"), pk=pk)
    seen = request.data.get("seen", True) not in (False, "false", "0", 0)
    if alert.seen != seen:
        alert.seen = seen
        alert.seen_at = timezone.now() if seen else None
        alert.save(update_fields=["seen", "seen_at"])
    return Response(s.AlertSerializer(alert).data)
