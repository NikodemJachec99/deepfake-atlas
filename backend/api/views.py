import asyncio
import json

from asgiref.sync import sync_to_async
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ads.models import Ad, Analysis
from evidence import store
from evidence.kinds import BAND_KINDS, FAMILIES, KINDS
from evidence.models import AdMarker, Artifact, AuditLog
from similarity.models import Campaign, Edge
from similarity.service import assign_campaign
from workflows import runner

from . import serializers as s


@extend_schema(request=s.AnalysisCreateSerializer, responses={201: s.AnalysisSerializer})
@api_view(["POST"])
def analysis_create(request):
    """Tryb Discovery: przyjmuje URL albo tekst i uruchamia analizę. Postęp idzie strumieniem `events_url`."""
    payload = s.AnalysisCreateSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    analysis = Analysis.objects.create(input_kind=payload.validated_data["kind"], input_value=payload.validated_data["value"])
    runner.start(str(analysis.pk))
    analysis.refresh_from_db()
    return Response(s.AnalysisSerializer(analysis).data, status=status.HTTP_201_CREATED)


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
        queryset = Ad.objects.select_related("membership__campaign").order_by("-id")
        if source := self.request.query_params.get("source"):
            queryset = queryset.filter(source=source)
        if campaign := self.request.query_params.get("campaign"):
            queryset = queryset.filter(membership__campaign_id=campaign)
        if query := self.request.query_params.get("q"):
            queryset = queryset.filter(Q(title__icontains=query) | Q(text__icontains=query) | Q(landing_url__icontains=query))
        return queryset


class AdDetail(generics.RetrieveAPIView):
    queryset = Ad.objects.select_related("advertiser", "membership__campaign")
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


class CampaignList(generics.ListAPIView):
    serializer_class = s.CampaignSerializer

    def get_queryset(self):
        return Campaign.objects.filter(merged_into__isnull=True).annotate(size=Count("memberships")).order_by("-size", "id")


@api_view(["GET"])
def campaign_detail(request, pk):
    """Kampania: reklamy, krawędzie między nimi i markery rdzeniowe, czyli te, które ją spinają."""
    campaign = get_object_or_404(Campaign.objects.annotate(size=Count("memberships")), pk=pk)
    ad_ids = list(campaign.memberships.values_list("ad_id", flat=True))
    ads = Ad.objects.filter(pk__in=ad_ids).select_related("membership__campaign").order_by("first_seen", "id")
    edges = Edge.objects.filter(ad_a_id__in=ad_ids, ad_b_id__in=ad_ids)
    core = (
        AdMarker.objects.filter(ad_id__in=ad_ids)
        .exclude(marker__kind__in=BAND_KINDS)
        .values("marker__kind", "marker__value", "marker__ad_count")
        .annotate(in_campaign=Count("ad_id"))
        .filter(in_campaign__gte=2)
        .order_by("-in_campaign")[:50]
    )
    return Response(
        {
            **s.CampaignSerializer(campaign).data,
            "ads": s.AdListSerializer(ads, many=True).data,
            "edges": s.EdgeSerializer(edges, many=True).data,
            "core_markers": [
                {
                    "kind": row["marker__kind"],
                    "label": KINDS[row["marker__kind"]].label,
                    "family": KINDS[row["marker__kind"]].family,
                    "value": row["marker__value"],
                    "in_campaign": row["in_campaign"],
                    "ad_count": row["marker__ad_count"],
                }
                for row in core
            ],
        }
    )


@api_view(["GET"])
def graph(request):
    """Graf dla Sigma.js. `?campaign=ID` albo `?ad=ID` (reklama z sąsiadami), inaczej wszystkie krawędzie do limitu."""
    edges = Edge.objects.all()
    if campaign := request.query_params.get("campaign"):
        ad_ids = list(Campaign.objects.get(pk=campaign).memberships.values_list("ad_id", flat=True))
        edges = edges.filter(Q(ad_a_id__in=ad_ids) | Q(ad_b_id__in=ad_ids))
    elif ad := request.query_params.get("ad"):
        edges = edges.filter(Q(ad_a_id=ad) | Q(ad_b_id=ad))
    edges = list(edges.order_by("-probability")[: int(request.query_params.get("limit", 2000))])
    node_ids = {e.ad_a_id for e in edges} | {e.ad_b_id for e in edges}
    if ad := request.query_params.get("ad"):
        node_ids.add(int(ad))
    nodes = Ad.objects.filter(pk__in=node_ids).select_related("membership__campaign")
    return Response(
        {
            "nodes": [
                {
                    "id": n.pk,
                    "label": n.title or n.landing_url or f"Reklama {n.pk}",
                    "source": n.source,
                    "campaign": n.membership.campaign.key if hasattr(n, "membership") else None,
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
                    "probability": e.probability,
                    "family": max(e.families, key=e.families.get) if e.families else None,
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


def artifact(request, sha256):
    """Surowy dowód. Zawsze jako załącznik tekstowy: to bywa złośliwy HTML i nie może się wyrenderować."""
    item = get_object_or_404(Artifact, pk=sha256)
    response = HttpResponse(store.get(item.sha256), content_type="text/plain; charset=utf-8" if "html" in item.kind else "application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{item.sha256[:16]}.{item.kind}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


@api_view(["POST"])
def ad_recluster(request, pk):
    """Ponownie przypisuje reklamę do kampanii, np. po odrzuceniu krawędzi."""
    return Response(assign_campaign(get_object_or_404(Ad, pk=pk)))
