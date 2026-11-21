"""Start analizy. O tym, gdzie się wykona, decyduje ANALYSIS_RUNNER."""

import asyncio
import threading

from django.conf import settings
from django.db import close_old_connections

from . import pipeline


def _in_thread(analysis_id: str) -> None:
    try:
        pipeline.run_all(analysis_id)
    finally:
        close_old_connections()


async def _start_workflow(analysis_id: str) -> None:
    from temporalio.client import Client

    client = await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)
    await client.start_workflow(
        "AnalyzeAd", analysis_id, id=f"analysis-{analysis_id}", task_queue=settings.TEMPORAL_TASK_QUEUE
    )


def _hunt_in_thread(run_id: str) -> None:
    from hunting import service

    try:
        service.execute(run_id)
    except Exception:  # noqa: BLE001  błąd jest zapisany w przebiegu
        pass
    finally:
        close_old_connections()


async def _start_hunt_workflow(run_id: str) -> None:
    from temporalio.client import Client

    client = await Client.connect(settings.TEMPORAL_ADDRESS, namespace=settings.TEMPORAL_NAMESPACE)
    await client.start_workflow(
        "HuntOperators", args=[run_id, {}], id=f"hunt-{run_id}", task_queue=settings.TEMPORAL_TASK_QUEUE
    )


def start_hunt(run_id: str) -> str:
    """Start przebiegu łowcy domen. Ten sam wybór miejsca wykonania co przy analizie (ANALYSIS_RUNNER)."""
    runner = settings.ANALYSIS_RUNNER
    if runner == "temporal":
        asyncio.run(_start_hunt_workflow(run_id))
    elif runner == "sync":
        from hunting import service

        try:
            service.execute(run_id)
        except Exception:  # noqa: BLE001  błąd jest zapisany w przebiegu
            pass
    else:
        threading.Thread(target=_hunt_in_thread, args=(run_id,), daemon=True).start()
    return runner


def start(analysis_id: str) -> str:
    runner = settings.ANALYSIS_RUNNER
    if runner == "temporal":
        asyncio.run(_start_workflow(analysis_id))
    elif runner == "sync":
        pipeline.run_all(analysis_id)
    else:
        threading.Thread(target=_in_thread, args=(analysis_id,), daemon=True).start()
    return runner
