import asyncio
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

# Skany startowe. Słowa-ziarna do bibliotek reklam dojdą z listy nadużywanych wizerunków i marek.
SCHEDULES = [
    ("scan-cert-pl", "cert_pl", {}, timedelta(minutes=15)),
    ("scan-microsoft-inwestycje", "microsoft", {"query": "inwestycje", "limit": 200}, timedelta(hours=6)),
    ("scan-microsoft-zarabiaj", "microsoft", {"query": "zarabiaj", "limit": 200}, timedelta(hours=6)),
]


class Command(BaseCommand):
    help = "Zakłada w Temporalu harmonogramy skanów źródeł. Istniejących nie rusza."

    def handle(self, *args, **options):
        asyncio.run(self._ensure())

    async def _ensure(self):
        from temporalio.client import (
            Client,
            Schedule,
            ScheduleActionStartWorkflow,
            ScheduleAlreadyRunningError,
            ScheduleIntervalSpec,
            ScheduleSpec,
        )

        client = await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)
        for schedule_id, collector, params, every in SCHEDULES:
            schedule = Schedule(
                action=ScheduleActionStartWorkflow(
                    "ScanSource", args=[collector, params], id=f"{schedule_id}-run", task_queue=settings.TEMPORAL_TASK_QUEUE
                ),
                spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=every)]),
            )
            try:
                await client.create_schedule(schedule_id, schedule)
                self.stdout.write(self.style.SUCCESS(f"Utworzono: {schedule_id}"))
            except ScheduleAlreadyRunningError:
                self.stdout.write(f"Już istnieje: {schedule_id}")
