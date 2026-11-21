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

# Łowca domen odpytuje crt.sh i pobiera strony oszustów przez crawlera, więc zakładamy go wstrzymany.
# Włącza go `--resume-hunt` (raz na dobę, certyfikaty z ostatnich 3 dni, 12 zapytań do crt.sh).
HUNT_SCHEDULE = ("hunt-operators", {"days": 3, "max_queries": 12, "max_crawl": 20}, timedelta(hours=24))


class Command(BaseCommand):
    help = (
        "Zakłada w Temporalu harmonogramy skanów źródeł. Istniejących nie rusza. "
        "--pause wstrzymuje skany bibliotek reklam (np. na czas demo, żeby korpus się nie zmieniał), --resume je wznawia."
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--pause", action="store_true", help="Wstrzymaj skany bibliotek reklam")
        group.add_argument("--resume", action="store_true", help="Wznów skany bibliotek reklam")
        group.add_argument("--resume-hunt", action="store_true", help="Włącz harmonogram łowcy domen (domyślnie wstrzymany)")
        group.add_argument("--pause-hunt", action="store_true", help="Wstrzymaj harmonogram łowcy domen")

    def handle(self, *args, **options):
        if options["resume_hunt"] or options["pause_hunt"]:
            asyncio.run(self._toggle_hunt(pause=options["pause_hunt"]))
        elif options["pause"] or options["resume"]:
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

    async def _toggle_hunt(self, pause: bool):
        from temporalio.client import Client
        from temporalio.service import RPCError

        client = await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)
        handle = client.get_schedule_handle(HUNT_SCHEDULE[0])
        try:
            if pause:
                await handle.pause(note="łowca domen wstrzymany")
            else:
                await handle.unpause(note="łowca domen włączony")
            self.stdout.write(f"{'Wstrzymano' if pause else 'Włączono'}: {HUNT_SCHEDULE[0]}")
        except RPCError as exc:
            self.stdout.write(f"Brak harmonogramu {HUNT_SCHEDULE[0]}: {exc}")

    async def _ensure(self):
        from temporalio.client import (
            Client,
            Schedule,
            ScheduleActionStartWorkflow,
            ScheduleAlreadyRunningError,
            ScheduleIntervalSpec,
            ScheduleSpec,
            ScheduleState,
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

        hunt_id, hunt_params, hunt_every = HUNT_SCHEDULE
        hunt = Schedule(
            action=ScheduleActionStartWorkflow(
                "HuntOperators", args=["", hunt_params], id=f"{hunt_id}-run", task_queue=settings.TEMPORAL_TASK_QUEUE
            ),
            spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=hunt_every)]),
            state=ScheduleState(
                paused=True,
                note="Łowca domen: nowe domeny znanych operatorów z crt.sh. Wstrzymany, włącz: ensure_schedules --resume-hunt",
            ),
        )
        try:
            await client.create_schedule(hunt_id, hunt)
            self.stdout.write(self.style.SUCCESS(f"Utworzono (wstrzymany): {hunt_id}"))
        except ScheduleAlreadyRunningError:
            self.stdout.write(f"Już istnieje: {hunt_id}")
