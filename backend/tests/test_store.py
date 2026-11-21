import pytest

from evidence import store
from evidence.models import Artifact

pytestmark = pytest.mark.django_db


def test_put_is_content_addressed():
    first = store.put(b"<html>a</html>", kind="html_victim", content_type="text/html")
    second = store.put(b"<html>a</html>", kind="html_victim")
    assert first.pk == second.pk and len(first.pk) == 64
    assert Artifact.objects.count() == 1
    assert store.get(first.pk) == b"<html>a</html>"


def test_put_restores_object_missing_from_backend():
    # Wpis w bazie nie gwarantuje pliku: magazyn mógł zostać podmieniony albo zapis się nie udał.
    artifact = store.put(b"dowod", kind="favicon")
    (store.backend().root / artifact.storage_key).unlink()
    store.put(b"dowod", kind="favicon")
    assert store.get(artifact.pk) == b"dowod"
