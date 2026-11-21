"""Eksport STIX 2.1. Dane zmyślone, z importu dwóch spraw na wspólnym zapleczu."""

import json
import re

import pytest
from rest_framework.test import APIClient

from ads.models import Ad
from collectors import bundle
from similarity.models import Operator, OperatorMembership
from tests.test_bundle import ARTICLE_X, make_case, run

pytestmark = pytest.mark.django_db
ID = re.compile(r"^[a-z0-9-]+--[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def fetch(client, query=""):
    response = client.get(f"/api/export/stix{query}")
    assert response.status_code == 200, response.content
    assert response["Content-Type"].startswith("application/stix+json")
    return json.loads(response.content)


def test_bundle_is_valid_stix_with_operator_campaign_and_indicators(tmp_path):
    for name, domain in (("1", "civic.example"), ("2", "across.example")):
        run(bundle.import_case(make_case(tmp_path, name, domain, "Zamach na biznesmena", ARTICLE_X), bundle="t"))
    data = fetch(APIClient())
    assert data["type"] == "bundle" and ID.match(data["id"])
    by_type: dict[str, list] = {}
    ids = set()
    for obj in data["objects"]:
        assert obj["spec_version"] == "2.1" and ID.match(obj["id"]) and obj["id"].startswith(obj["type"] + "--")
        assert TIME.match(obj["created"]) and TIME.match(obj["modified"])
        ids.add(obj["id"])
        by_type.setdefault(obj["type"], []).append(obj)
    assert len(by_type["intrusion-set"]) == 1 and len(by_type["campaign"]) == 1
    patterns = {i["pattern"] for i in by_type["indicator"]}
    assert "[domain-name:value = 'civic.example']" in patterns and "[domain-name:value = 'across.example']" in patterns
    assert all(i["pattern_type"] == "stix" and TIME.match(i["valid_from"]) for i in by_type["indicator"])
    for rel in by_type["relationship"]:
        assert rel["source_ref"] in ids and rel["target_ref"] in ids
    identifiers = {i["type"] for i in by_type["intrusion-set"][0]["x_scamdna_identifiers"]}
    assert "funnel_id" in identifiers  # ślad konta operatora bez obiektu STIX idzie do właściwości
    text = json.dumps(data)
    assert "person:" not in text and "sha256-" not in text  # bez osób i tokenów


def test_library_ads_are_never_exported_as_intrusion_sets():
    legit = [Ad.objects.create(source="microsoft", external_id=f"ms-{i}") for i in range(2)]
    operator = Operator.objects.create()
    for ad in legit:
        OperatorMembership.objects.create(ad=ad, operator=operator)
    data = fetch(APIClient())
    assert [o["type"] for o in data["objects"]] == ["identity"]


def test_filters_and_stable_ids(tmp_path):
    for name, domain in (("1", "civic.example"), ("2", "across.example")):
        run(bundle.import_case(make_case(tmp_path, name, domain, "Zamach", ARTICLE_X), bundle="t"))
    operator = Operator.objects.get()
    client = APIClient()
    first, second = fetch(client, f"?operator={operator.pk}"), fetch(client, f"?operator={operator.pk}")
    assert {o["id"] for o in first["objects"]} == {o["id"] for o in second["objects"]}
    assert [o["type"] for o in fetch(client, "?operator=999999")["objects"]] == ["identity"]
    assert client.get("/api/export/stix?operator=abc").status_code == 400
