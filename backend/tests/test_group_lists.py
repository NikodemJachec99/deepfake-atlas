"""Listy kampanii i operatorów: skład grup według źródła i filtr ?source=. Dane zmyślone."""

import pytest
from rest_framework.test import APIClient

from ads.models import Ad
from similarity.models import Campaign, CampaignMembership, Operator, OperatorMembership

pytestmark = pytest.mark.django_db


def group(ads: list[Ad]) -> tuple[Campaign, Operator]:
    campaign, operator = Campaign.objects.create(), Operator.objects.create()
    for ad in ads:
        CampaignMembership.objects.create(ad=ad, campaign=campaign)
        OperatorMembership.objects.create(ad=ad, operator=operator)
    return campaign, operator


def ad(source: str, case: str | None = None, listed: bool = False) -> Ad:
    labels = {**({"case": case} if case else {}), **({"cert_pl": {"domain": "x.example"}} if listed else {})}
    return Ad.objects.create(source=source, external_id=f"{source}/{Ad.objects.count()}", labels=labels)


@pytest.fixture
def groups():
    library = group([ad("microsoft") for _ in range(5)])
    cases = group([ad("capture", "1", listed=True), ad("capture", "p1"), ad("capture", "p2"), ad("capture", "p2")])
    mixed = group([ad("capture", "48"), ad("microsoft")])
    return {"library": library, "cases": cases, "mixed": mixed}


@pytest.mark.parametrize("path, index", [("/api/campaigns", 0), ("/api/operators", 1)])
def test_lists_show_sources_cases_and_cert(groups, path, index):
    rows = {r["id"]: r for r in APIClient().get(path).json()["results"]}
    library, cases, mixed = (groups[k][index].pk for k in ("library", "cases", "mixed"))
    assert [r["id"] for r in APIClient().get(path).json()["results"]] == [library, cases, mixed]  # nadal od największej
    assert (rows[library]["sources"], rows[library]["cases"], rows[library]["cert_pl"]) == ({"microsoft": 5}, 0, 0)
    assert (rows[cases]["sources"], rows[cases]["cases"], rows[cases]["cert_pl"]) == ({"capture": 4}, 3, 1)
    assert rows[mixed]["sources"] == {"capture": 1, "microsoft": 1} and rows[mixed]["size"] == 2


@pytest.mark.parametrize("path, index", [("/api/campaigns", 0), ("/api/operators", 1)])
def test_source_filter_keeps_groups_with_that_source(groups, path, index):
    client = APIClient()
    only_cases = [r["id"] for r in client.get(f"{path}?source=capture").json()["results"]]
    assert only_cases == [groups["cases"][index].pk, groups["mixed"][index].pk]
    # rozmiar i skład zostają pełne, filtr tylko wybiera grupy
    mixed = next(r for r in client.get(f"{path}?source=capture").json()["results"] if r["id"] == groups["mixed"][index].pk)
    assert mixed["size"] == 2 and mixed["sources"] == {"capture": 1, "microsoft": 1}
    assert [r["id"] for r in client.get(f"{path}?source=meta").json()["results"]] == []
    both = [r["id"] for r in client.get(f"{path}?source=capture,microsoft").json()["results"]]
    assert len(both) == 3


def test_query_count_does_not_grow_with_groups(groups, django_assert_max_num_queries):
    for _ in range(10):
        group([ad("microsoft")])
    with django_assert_max_num_queries(8):
        APIClient().get("/api/operators")
