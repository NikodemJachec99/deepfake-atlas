from django.core.management.base import BaseCommand

from similarity import service
from similarity.models import CampaignMembership, OperatorMembership


class Command(BaseCommand):
    help = "Przelicza wszystkie aktywne kampanie i grupy operatorów: rozdziela te, które nie są już spójne po decyzjach."

    def handle(self, *args, **options):
        ad_ids = set(CampaignMembership.objects.values_list("ad_id", flat=True)) | set(
            OperatorMembership.objects.values_list("ad_id", flat=True)
        )
        result = service.recluster(sorted(ad_ids))
        for name, changes in result.items():
            self.stdout.write(f"{name}: rozdzielono {len(changes)} grup")
            for change in changes:
                parts = ", ".join(f"{p['key']}={len(p['ads'])}" for p in change["after"])
                self.stdout.write(f"  {change['group']} ({len(change['before'])} reklam) -> {parts or '-'}, bez grupy: {len(change['released'])}")
