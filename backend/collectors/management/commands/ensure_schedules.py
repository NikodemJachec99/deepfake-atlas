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
    help = (
        "Zakłada w Temporalu harmonogramy skanów źródeł. Istniejących nie rusza. "
        "--pause wstrzymuje skany bibliotek reklam (np. na czas demo, żeby korpus się nie zmieniał), --resume je wznawia."
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--pause", action="store_true", help="Wstrzymaj skany bibliotek reklam")
        group.add_argument("--resume", action="store_true", help="Wznów skany bibliotek reklam")

    def handle(self, *args, **options):
        if options["pause"] or options["resume"]:
            asyncio.run(self._toggle(pause=options["pause"]))
        else:
            asyncio.run(self._ensure())

    async def _toggle(self, pause: bool):
        from temporalio.client import Client
        from temporalio.service import RPCError

        client = await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)
        # Lista CERT Polska tylko odświeża etykiety domen i nie dodaje reklam, więc zostaje włączona.
        for schedule_id, collector, _params, _every in SCHEDULES:
            if collector == "cert_pl":
                continue
            handle = client.get_schedule_handle(schedule_id)
            try:
                if pause:
                    await handle.pause(note="wstrzymane na czas demo")
                else:
                    await handle.unpause(note="wznowione")
                self.stdout.write(f"{'Wstrzymano' if pause else 'Wznowiono'}: {schedule_id}")
            except RPCError as exc:
                self.stdout.write(f"Brak harmonogramu {schedule_id}: {exc}")

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
