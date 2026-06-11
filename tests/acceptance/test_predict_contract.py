"""Acceptance: the model API honours its request/response contract.

- Given the API contract, a valid request returns the expected response format.
- Given an invalid request, the API returns an explicit error without crashing.
"""
from __future__ import annotations


def test_valid_request_returns_expected_format(client):
    response = client.post("/predict", json={"text": "Très bon produit, je recommande."})
    assert response.status_code == 200
    body = response.json()
    assert {"prediction", "model", "version"}.issubset(body)
    assert isinstance(body["prediction"], dict)


def test_invalid_request_returns_explicit_error(client):
    response = client.post("/predict", json={"unexpected_field": 123})
    assert response.status_code in (400, 422)
    assert "detail" in response.json()
