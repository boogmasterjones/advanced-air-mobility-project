"""Test setup: tests never touch the network."""
import os

import pytest

os.environ["ROUTE_LOOKUP"] = "cache"   # roads.py: saved routes or the model, never live OSRM
os.environ["LLM_PROVIDER"] = "offline"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("tests must not use the network")

    monkeypatch.setattr("httpx.get", refuse)
    monkeypatch.setattr("httpx.post", refuse)
