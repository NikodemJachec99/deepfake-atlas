"""Worker Temporal. Uruchomienie: python -m workflows.worker"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

import django


async def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scamdna.settings")
    django.setup()

    from django.conf import settings
    from temporalio.client import Client
    from temporalio.worker import Worker

    from . import activities
    from .temporal_workflows import AnalyzeAdWorkflow, HuntOperatorsWorkflow, ScanSourceWorkflow

    client = await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)
    worker = Worker(
        client,
        task_queue=settings.TEMPORAL_TASK_QUEUE,
        workflows=[AnalyzeAdWorkflow, ScanSourceWorkflow, HuntOperatorsWorkflow],
        activities=activities.ALL,
        activity_executor=ThreadPoolExecutor(max_workers=8),
    )
    print(f"Worker słucha kolejki {settings.TEMPORAL_TASK_QUEUE} na {settings.TEMPORAL_ADDRESS}", flush=True)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
