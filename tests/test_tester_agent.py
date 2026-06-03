from agents.tester import _extract_safe_test_functions, _fallback_route_test


def test_extract_safe_test_functions_skips_fixtures_and_marks_llm_tests_xfail():
    raw_output = """
import pytest
from flask import Flask

@pytest.fixture
def app():
    return Flask(__name__)

def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200

def test_needs_external_fixture(client, db_session):
    assert db_session is not None
"""

    functions = _extract_safe_test_functions(raw_output, route_index=1)

    assert len(functions) == 1
    assert "def llm_1_test_home_page(client):" in functions[0]
    assert "@pytest.mark.xfail" in functions[0]
    assert "test_needs_external_fixture" not in functions[0]


def test_fallback_route_test_generates_smoke_test_for_post_route():
    route = {"method": "POST", "path": "/create-note", "description": "Creates a note"}

    test_code = _fallback_route_test(route, route_index=3)

    assert "def test_route_3_post_create_note_smoke(client):" in test_code
    assert "client.post('/create-note', data={})" in test_code
    assert "assert response.status_code < 500" in test_code
