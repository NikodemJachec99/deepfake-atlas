"""Ustawienia testów: bez sieci, analiza synchroniczna, dowody w katalogu tymczasowym."""

import tempfile
from pathlib import Path

from .settings import *  # noqa: F403

ANALYSIS_RUNNER = "sync"
ARTIFACT_BACKEND = "local"
ARTIFACT_DIR = Path(tempfile.mkdtemp(prefix="scamdna-artifacts-"))
CRAWLER_FETCHER = "tests.fakes.FakeFetcher"
ENRICHER = "tests.fakes.FakeEnricher"
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"analyses": "100000/min"}}  # noqa: F405
