import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Prefetch

from ads.models import Ad
from evidence.kinds import FAMILIES, KINDS
from evidence.models import AdMarker
from extractors.url import redact_url
from similarity.fusion import MODEL_VERSION
from similarity.models import Edge, EdgeEvidence

# Pasma LSH to klucze wyszukiwania, nie cechy. W eksporcie tylko zaśmiecają.
SKIPPED_KINDS = {code for code, kind in KINDS.items() if kind.cap <= 0}


def campaign_key(ad: Ad) -> str:
    return ad.membership.campaign.key if hasattr(ad, "membership") else ""


def operator_key(ad: Ad) -> str:
    return ad.operator_membership.operator.key if hasattr(ad, "operator_membership") else ""


class Command(BaseCommand):
    help = "Zapisuje wzbogacony korpus do plików: reklamy z markerami, krawędzie z dowodami, kampanie i operatorów."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Katalog docelowy, powstanie, jeśli go nie ma")

    def handle(self, *args, **options):
        out = Path(options["path"])
        out.mkdir(parents=True, exist_ok=True)
        ads = list(
            Ad.objects.select_related("membership__campaign", "operator_membership__operator")
            .prefetch_related(Prefetch("ad_markers", queryset=AdMarker.objects.select_related("marker", "artifact")))
            .order_by("id")
        )
        edges = list(
            Edge.objects.select_related("ad_a", "ad_b")
            .prefetch_related(Prefetch("evidence", queryset=EdgeEvidence.objects.order_by("-weight_bits")))
            .order_by("id")
        )

        with (out / "reklamy.jsonl").open("w", encoding="utf-8") as f:
            for ad in ads:
                f.write(json.dumps(self.ad_row(ad), ensure_ascii=False) + "\n")
        with (out / "krawedzie.jsonl").open("w", encoding="utf-8") as f:
            for edge in edges:
                f.write(json.dumps(self.edge_row(edge), ensure_ascii=False) + "\n")
        with (out / "grupy.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["reklama", "external_id", "paczka", "sprawa", "kampania", "operator", "lista_cert"])
            for ad in ads:
                writer.writerow(
                    [ad.id, ad.external_id, ad.labels.get("bundle", ""), ad.labels.get("case", ""), campaign_key(ad), operator_key(ad), int("cert_pl" in ad.labels)]
                )

        summary = {
            "utworzono": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": MODEL_VERSION,
            "reklamy": len(ads),
            "krawedzie": dict(Counter(e.relation for e in edges)),
            "kampanie": len({campaign_key(a) for a in ads} - {""}),
            "operatorzy": len({operator_key(a) for a in ads} - {""}),
            "rodziny": FAMILIES,
            "pliki": {
                "reklamy.jsonl": "jedna reklama w wierszu: dane, przypisanie do kampanii i operatora, markery z rodziną i liczbą reklam z tą wartością",
                "krawedzie.jsonl": "jedna krawędź w wierszu: relacja, pewność, bity i lista dowodów z wkładem każdego",
                "grupy.csv": "przypisanie reklam do kampanii i operatorów",
            },
        }
        (out / "opis.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Zapisano do {out}: {len(ads)} reklam, {len(edges)} krawędzi"))

    def ad_row(self, ad: Ad) -> dict:
        markers = []
        for link in ad.ad_markers.all():
            marker = link.marker
            if marker.kind in SKIPPED_KINDS or marker.kind not in KINDS:
                continue
            kind = KINDS[marker.kind]
            markers.append(
                {
                    "family": kind.family,
                    "kind": marker.kind,
                    "label": kind.label,
                    "value": marker.value,
                    "ads_with_value": marker.ad_count,
                    "artifact": link.artifact_id or "",
                }
            )
        markers.sort(key=lambda m: (m["family"], m["kind"], m["value"]))
        return {
            "id": ad.id,
            "source": ad.source,
            "external_id": ad.external_id,
            "bundle": ad.labels.get("bundle", ""),
            "case": ad.labels.get("case", ""),
            "title": ad.title,
            "landing_url": redact_url(ad.landing_url) if ad.landing_url else "",
            "first_seen": ad.first_seen.isoformat() if ad.first_seen else None,
            "topics": ad.labels.get("topics", []),
            "keywords": ad.labels.get("keywords", []),
            "cert_pl": ad.labels.get("cert_pl"),
            "campaign": campaign_key(ad),
            "operator": operator_key(ad),
            "markers": markers,
        }

    def edge_row(self, edge: Edge) -> dict:
        return {
            "id": edge.id,
            "ad_a": edge.ad_a_id,
            "ad_b": edge.ad_b_id,
            "ad_a_external_id": edge.ad_a.external_id,
            "ad_b_external_id": edge.ad_b.external_id,
            "relation": edge.relation,
            "duplicate": edge.duplicate,
            "probability": round(edge.probability, 6),
            "bits": round(edge.bits, 2),
            "families": {k: round(v, 2) for k, v in edge.families.items()},
            "model_version": edge.model_version,
            "verdict": edge.verdict,
            "evidence": [
                {
                    "family": ev.family,
                    "kind": ev.kind,
                    "value_a": ev.value_a,
                    "value_b": ev.value_b,
                    "similarity": round(ev.similarity, 4),
                    "df": ev.df,
                    "corpus_n": ev.corpus_n,
                    "weight_bits": round(ev.weight_bits, 2),
                    "decisive": ev.decisive,
                }
                for ev in edge.evidence.all()
            ],
        }
