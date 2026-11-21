from django.conf import settings
from django.core.management.base import BaseCommand

from ads.models import Ad
from extractors.url import host_of, registered_domain

MAPPING = {
    "mappings": {
        "properties": {
            "source": {"type": "keyword"},
            "title": {"type": "text"},
            "text": {"type": "text"},
            "landing_url": {"type": "keyword"},
            "domain": {"type": "keyword"},
            "advertiser": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
            "campaign": {"type": "keyword"},
            "cert_pl_listed": {"type": "boolean"},
            "first_seen": {"type": "date"},
        }
    }
}


class Command(BaseCommand):
    help = "Odbudowuje indeks pełnotekstowy reklam w OpenSearch z Postgresa."

    def handle(self, *args, **options):
        from opensearchpy import OpenSearch, helpers

        client = OpenSearch(settings.OPENSEARCH_URL)
        index = settings.OPENSEARCH_INDEX
        if client.indices.exists(index=index):
            client.indices.delete(index=index)
        client.indices.create(index=index, body=MAPPING)

        def actions():
            for ad in Ad.objects.select_related("advertiser", "membership__campaign").iterator(chunk_size=1000):
                membership = getattr(ad, "membership", None)
                yield {
                    "_index": index,
                    "_id": ad.pk,
                    "_source": {
                        "source": ad.source,
                        "title": ad.title,
                        "text": ad.text,
                        "landing_url": ad.landing_url,
                        "domain": registered_domain(host_of(ad.landing_url)) if ad.landing_url else None,
                        "advertiser": ad.advertiser.name if ad.advertiser else None,
                        "campaign": membership.campaign.key if membership else None,
                        "cert_pl_listed": "cert_pl" in ad.labels,
                        "first_seen": ad.first_seen,
                    },
                }

        indexed, _ = helpers.bulk(client, actions())
        client.indices.refresh(index=index)
        self.stdout.write(self.style.SUCCESS(f"OpenSearch: zaindeksowano {indexed} reklam w indeksie {index}"))
