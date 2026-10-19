"""All fixtures are synthetic: tests never contact production."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def quota_html():
    return (Path(__file__).parent / "fixtures" / "quota.html").read_text()


@pytest.fixture
def login_html():
    return (Path(__file__).parent / "fixtures" / "login.html").read_text()
