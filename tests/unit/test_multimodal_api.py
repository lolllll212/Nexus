"""Test the multimodal API endpoint."""

import pytest
from starlette.testclient import TestClient
from nexus.infrastructure.api.main import create_app


AUTH_HEADERS = {"Authorization": "Bearer sk-test-1"}


def test_multimodal_api_sample():
    app = create_app()
    client = TestClient(app, headers=AUTH_HEADERS)
    response = client.get("/api/multimodal/samples")
    assert response.status_code == 200
    data = response.json()
    assert "samples" in data
    assert len(data["samples"]) >= 3


def test_multimodal_api_process_mock():
    app = create_app()
    client = TestClient(app, headers=AUTH_HEADERS)
    response = client.post(
        "/api/multimodal/process",
        data={
            "source_url": "https://example.com/hud_preview.png",
            "media_type": "image",
            "question": "What is the primary color scheme?",
        },
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["media_type"] == "image"
    assert "prompt_injection_block" in res_data
    assert "spatial_grid" in res_data["decomposition"]
