"""reset_corpus czyści też przesłanki, alerty i łowcę, żeby nowy korpus nie dziedziczył zakwestionowanych śladów."""

import pytest
from django.core.management import call_command

from ads.models import Ad
from similarity.models import Premise

pytestmark = pytest.mark.django_db


def test_reset_removes_premises():
    Ad.objects.create(source="manual", external_id="r1")
    Premise.objects.create(kind="ga4", value="G-RESET00000", reason="test")
    call_command("reset_corpus", "--yes")
    assert Ad.objects.count() == 0
    assert Premise.objects.count() == 0
