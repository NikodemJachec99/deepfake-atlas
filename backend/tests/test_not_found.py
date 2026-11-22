"""Komunikaty 404 po polsku, także z get_object_or_404 i widoków spoza DRF."""

import pytest
from rest_framework.test import APIClient

from api.errors import not_found_detail

pytestmark = pytest.mark.django_db


def test_missing_group_and_edge_say_it_in_polish():
    client = APIClient()
    for url, word in (("/api/campaigns/99999", "kampanii"), ("/api/operators/99999", "operatora"), ("/api/edges/99999", "krawędzi")):
        response = client.get(url)
        assert response.status_code == 404
        assert response.json()["detail"] == f"Nie ma {word} o tym identyfikatorze."


def test_package_of_missing_group_is_polish_json():
    response = APIClient().get("/api/campaigns/99999/package")
    assert response.status_code == 404
    assert response.json()["detail"].startswith("Nie ma kampanii")


def test_missing_artifact_image_outside_drf_is_json():
    response = APIClient().get("/api/artifacts/" + "0" * 64 + "/image")
    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert response.json()["detail"].startswith("Nie ma")


def test_own_polish_messages_stay():
    assert not_found_detail("Żadna reklama nie ma takiego śladu.") == "Żadna reklama nie ma takiego śladu."
    assert not_found_detail("No Foo matches the given query.") == "Nie ma takiego obiektu o tym identyfikatorze."
