import pytest

from tests import fakes


@pytest.fixture(autouse=True)
def _clean_fakes():
    fakes.reset()
    yield
    fakes.reset()


@pytest.fixture(autouse=True)
def _no_model_downloads(settings):
    # Testy nie pobierają modeli z sieci. Kanał twarzy bez modelu po prostu nic nie zwraca.
    settings.FACE_MODELS_DOWNLOAD = False
    settings.EMBEDDINGS_DOWNLOAD = False
