"""Definicje workflow Temporal. Ten plik działa w piaskownicy Temporala, więc nie importuje Django.

Aktywności wołamy po nazwie. Ich kod jest w `workflows.activities`.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

STAGES = ["ingest", "crawl", "extract", "enrich", "fuse", "cluster"]

# Etapy sieciowe mogą trwać i zawodzić. Ponawiamy je, bo każdy zapisuje wynik idempotentnie.
STAGE_RETRY = RetryPolicy(initial_interval=timedelta(seconds=2), backoff_coefficient=2.0, maximum_attempts=3)


@workflow.defn(name="AnalyzeAd")
class AnalyzeAdWorkflow:
    @workflow.run
    async def run(self, analysis_id: str) -> str:
        try:
            for stage in STAGES:
                await workflow.execute_activity(
                    "run_stage",
                    args=[analysis_id, stage],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=STAGE_RETRY,
                )
        except Exception as exc:
            await workflow.execute_activity(
                "finish_analysis", args=[analysis_id, f"{type(exc).__name__}: {exc}"], start_to_close_timeout=timedelta(seconds=30)
            )
            raise
        await workflow.execute_activity("finish_analysis", args=[analysis_id, ""], start_to_close_timeout=timedelta(seconds=30))
        return analysis_id


@workflow.defn(name="ScanSource")
class ScanSourceWorkflow:
    """Skan jednego źródła według harmonogramu. Znalezione reklamy dostają własne workflow analizy."""

    @workflow.run
    async def run(self, collector: str, params: dict) -> dict:
        result = await workflow.execute_activity(
            "run_collector",
            args=[collector, params],
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
        for analysis_id in result.get("analyses", []):
            await workflow.start_child_workflow(
                "AnalyzeAd",
                analysis_id,
                id=f"analysis-{analysis_id}",
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
            )
        return result
