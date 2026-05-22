"""
Shared fixtures for API route tests.
"""

import json

import pytest
from flask_jwt_extended import create_access_token

from app import app


@pytest.fixture
def client():
    """
    Provide a Flask test client with JWT configured for route tests.
    """
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-key-which-is-longer-than-thirty-two",
    )
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    """
    Create Authorization headers for JWT-protected API routes.
    """

    def _auth_headers(identity="tester@example.com", role="admin", user_id=7):
        with app.app_context():
            token = create_access_token(
                identity=identity,
                additional_claims={"role": role, "user_id": user_id},
            )
        return {"Authorization": f"Bearer {token}"}

    return _auth_headers


@pytest.fixture
def parse_json_response():
    """
    Parse JSON responses returned as serialized strings.
    """

    def _parse_json_response(response):
        data = response.get_data(as_text=True)
        if not data:
            return None
        return json.loads(data)

    return _parse_json_response
