"""Uzupełnia wektory obrazów reklam (Ad.image_embedding) bez ponownego importu i skanu."""

from django.core.management.base import BaseCommand

from ads.models import Ad, Analysis
from extractors import image_embedding
from similarity import service


class Command(BaseCommand):
    help = "Liczy wektor obrazu (CLIP) dla reklam bez niego. --all przelicza wszystkie, --link dolicza krawędzie."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="przelicz także reklamy, które już mają wektor")
        parser.add_argument("--link", action="store_true", help="po policzeniu wektora ponownie dopasuj reklamę do korpusu")

    def handle(self, *args, **options):
        if not image_embedding.available():
            self.stderr.write("Brak modelu obrazu albo bibliotek (EMBEDDINGS_DOWNLOAD=0?).")
            return
        ads = Ad.objects.all() if options["all"] else Ad.objects.filter(image_embedding__isnull=True)
        done = skipped = 0
        for ad in ads.order_by("pk"):
            analysis = Analysis.objects.filter(ad=ad).order_by("-created_at").first()
            victim = ((analysis.state if analysis else {}).get("pages") or {}).get("victim") or {}
            vector = image_embedding.ad_vector(ad, victim)
            if vector is None:
                skipped += 1
                continue
            ad.image_embedding = vector
            ad.save(update_fields=["image_embedding"])
            if options["link"]:
                service.link_ad(ad)
            done += 1
        self.stdout.write(self.style.SUCCESS(f"Wektory obrazu: {done}, bez obrazu: {skipped}"))
