"""Aktywności Temporal. Cienka warstwa nad potokiem i kolektorami, uruchamiana w puli wątków."""

from django.db import close_old_connections
from temporalio import activity

from . import pipeline


@activity.defn(name="run_stage")
def run_stage(analysis_id: str, stage: str) -> dict:
    close_old_connections()
    return pipeline.run_stage(analysis_id, stage)


@activity.defn(name="finish_analysis")
def finish_analysis(analysis_id: str, error: str) -> None:
    close_old_connections()
    pipeline.finish(analysis_id, error=error)


@activity.defn(name="run_collector")
def run_collector(collector: str, params: dict) -> dict:
    close_old_connections()
    from collectors.registry import run

    return run(collector, params)


ALL = [run_stage, finish_analysis, run_collector]
