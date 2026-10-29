"""
Shared fixtures for BillClear tests.
Module-scoped fixtures call the API once per test session, not once per test method.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from app import app as flask_app

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_data")


def read_sample(fname):
    with open(os.path.join(SAMPLE_DIR, fname), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="session")
def flask_client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture(scope="module")
def bill_analysis(flask_client):
    """Run sample_bill.txt through the API once — shared across all bill tests."""
    resp = flask_client.post("/analyze", json={"text": read_sample("sample_bill.txt")})
    return resp.get_json(), resp.status_code


@pytest.fixture(scope="module")
def eob_analysis(flask_client):
    """Run sample_eob.txt through the API once — shared across all EOB tests."""
    resp = flask_client.post("/analyze", json={"text": read_sample("sample_eob.txt")})
    return resp.get_json(), resp.status_code


# Register the 'ai' mark so pytest doesn't warn
def pytest_configure(config):
    config.addinivalue_line("markers", "ai: marks tests that require Ollama to be running")
