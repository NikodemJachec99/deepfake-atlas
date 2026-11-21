import pytest

from tests import fakes


@pytest.fixture(autouse=True)
def _clean_fakes():
    fakes.reset()
    yield
    fakes.reset()
