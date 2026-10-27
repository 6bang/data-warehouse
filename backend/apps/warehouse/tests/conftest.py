import pytest
from cryptography.fernet import Fernet
import socket
from urllib import request


@pytest.fixture(autouse=True)
def ephemeral_integration_encryption_key(settings):
    """Each test gets a fresh, non-persistent key; no deployable key is shipped."""
    settings.INTEGRATION_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")


@pytest.fixture(autouse=True)
def forbid_unmocked_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unit tests must explicitly mock outbound network and DNS")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(request, "urlopen", forbidden)
