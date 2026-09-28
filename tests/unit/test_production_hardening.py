"""
Tests for production hardening features:
- SSRF Guard and URL validation
- Prometheus metrics endpoint and system telemetry
- Liveness and readiness probes (/healthz, /readyz)
- Multi-tier and token streaming for NVIDIA NIM
- GitHub webhook HMAC verification and Gmail push receiver
"""

import hashlib
import hmac
import pytest
from starlette.testclient import TestClient

from nexus.infrastructure.api.main import create_app
from nexus.infrastructure.adapters.security.ssrf import validate_safe_url, is_safe_ip
from nexus.infrastructure.api.routes.integrations import verify_github_signature


def test_ssrf_validator_blocks_private_and_metadata():
    # Loopback
    safe, err = validate_safe_url("http://127.0.0.1:8000/api")
    assert not safe
    assert "blocked" in err.lower() or "private" in err.lower()

    safe, err = validate_safe_url("http://localhost:3000")
    assert not safe

    # AWS/GCP Metadata
    safe, err = validate_safe_url("http://169.254.169.254/latest/meta-data")
    assert not safe

    # Private RFC 1918 networks
    safe, err = validate_safe_url("http://10.0.0.1/admin")
    assert not safe

    safe, err = validate_safe_url("http://192.168.1.1/router")
    assert not safe

    # Non-HTTP protocols
    safe, err = validate_safe_url("file:///etc/passwd")
    assert not safe
    assert "disallowed protocol" in err.lower()

    # Public URLs
    safe, err = validate_safe_url("https://example.com/api/v1")
    assert safe


def test_github_webhook_hmac_verification():
    secret = "nexus_production_secret"
    body = b'{"action": "opened", "issue": {"title": "Critical bug"}}'

    mac = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    valid_sig = f"sha256={mac.hexdigest()}"

    assert verify_github_signature(body, valid_sig, secret) is True
    assert verify_github_signature(body, "sha256=invalid_hash", secret) is False
    assert verify_github_signature(body, None, secret) is False


def test_liveness_and_readiness_probes():
    app = create_app()
    with TestClient(app) as client:
        # Liveness
        res_live = client.get("/healthz")
        assert res_live.status_code == 200
        data_live = res_live.json()
        assert data_live["status"] == "ok"
        assert "timestamp" in data_live

        # Readiness
        res_ready = client.get("/readyz")
        assert res_ready.status_code == 200
        data_ready = res_ready.json()
        assert data_ready["status"] == "ready"
        assert data_ready["checks"]["tools"] is True


def test_prometheus_metrics_endpoint():
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/metrics")
        assert res.status_code == 200
        text = res.text
        assert "nexus_uptime_seconds" in text
        assert "nexus_active_tools" in text
        assert "nexus_graph_nodes" in text
        assert "nexus_requests_total" in text

        # JSON Telemetry
        res_json = client.get("/api/system/telemetry")
        assert res_json.status_code == 200
        data = res_json.json()
        assert data["status"] == "online"
        assert data["tools_count"] >= 20
        assert "uptime_seconds" in data


def test_nim_streaming_endpoint():
    app = create_app()
    with TestClient(app) as client:
        res = client.post(
            "/api/nim/chat/stream",
            json={"prompt": "Provide production status report.", "tier": "cortex"},
        )
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")
        body = res.text
        assert "data:" in body
        assert "token" in body or "done" in body


def test_webhooks_endpoints():
    app = create_app()
    with TestClient(app) as client:
        # GitHub webhook
        res_gh = client.post(
            "/api/integrations/github/webhook",
            json={"action": "opened", "repository": {"full_name": "lolllll212/Nexus"}},
            headers={"X-GitHub-Event": "issues"},
        )
        assert res_gh.status_code == 200
        data_gh = res_gh.json()
        assert data_gh["status"] == "processed"
        assert data_gh["event"] == "issues"

        # Gmail webhook
        res_gm = client.post(
            "/api/integrations/gmail/webhook",
            json={"message": {"messageId": "msg-prod-999"}},
        )
        assert res_gm.status_code == 200
        data_gm = res_gm.json()
        assert data_gm["status"] == "received"
        assert data_gm["messageId"] == "msg-prod-999"


def test_request_id_and_head_probes():
    app = create_app()
    with TestClient(app) as client:
        # Check custom X-Request-ID propagation
        custom_id = "test-corr-id-12345"
        res = client.get("/healthz", headers={"X-Request-ID": custom_id})
        assert res.status_code == 200
        assert res.headers["x-request-id"] == custom_id
        assert "x-response-time-ms" in res.headers

        # Check HEAD probe support
        res_head = client.head("/healthz")
        assert res_head.status_code == 200

        res_ready_head = client.head("/readyz")
        assert res_ready_head.status_code == 200


def test_websocket_telemetry():
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            data = ws.receive_json()
            assert data["type"] == "telemetry_pulse"
            assert "uptime_seconds" in data
            assert data["tools_count"] >= 20
