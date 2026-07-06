"""Integration tests against the real FastAPI app. These require the live stack
(`docker compose up -d neo4j qdrant` at minimum, plus a real GEMINI_API_KEY in .env for
the /screen tests) -- consistent with this project's 'no mock provider' design. Run with:
    pytest tests/integration -v
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_substance_regulations_known_cas(client):
    resp = client.get("/substance/335-67-1/regulations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cas_number"] == "335-67-1"
    assert any(r["name"] == "PFAS_RESTRICTION_DRAFT" for r in body["regulations"])
    assert any(t["basis"] == "individual_pfas" for t in body["thresholds"])


def test_substance_regulations_unknown_cas_returns_404(client):
    resp = client.get("/substance/0-00-0/regulations")
    assert resp.status_code == 404


def test_screen_rejects_non_pdf_upload(client):
    resp = client.post("/screen", files={"file": ("not_a_pdf.txt", b"hello world", "text/plain")})
    assert resp.status_code == 422


def test_screen_rejects_unparseable_pdf(client):
    # Well-formed-looking filename but garbage bytes -- extract_text should raise ValueError -> 422
    resp = client.post("/screen", files={"file": ("empty.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")})
    assert resp.status_code == 422


def test_product_status_unknown_id_returns_404(client):
    resp = client.get("/product/does-not-exist/status")
    assert resp.status_code == 404


def test_review_queue_lists_pending_items(client):
    resp = client.get("/review/queue", params={"status": "pending"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_review_decision_rejects_invalid_decision_value(client):
    resp = client.post("/review/some-id/decision", json={"decision": "maybe", "decided_by": "tester"})
    assert resp.status_code == 422


def test_review_decision_unknown_item_returns_404(client):
    resp = client.post("/review/does-not-exist/decision", json={"decision": "approved", "decided_by": "tester"})
    assert resp.status_code == 404


@pytest.mark.slow
def test_screen_end_to_end_happy_path(client):
    """Full pipeline through a real PDF + real Gemini call -- marked slow since it costs
    an API call and takes a few seconds; skip with `-m "not slow"` for a fast test run."""
    import time
    from pathlib import Path

    pdf_path = Path(__file__).resolve().parent.parent.parent / "db" / "synthetic_sds" / "pdfs" / "doc-01.pdf"
    if not pdf_path.exists():
        pytest.skip("Synthetic PDFs not generated yet -- run db/synthetic_sds/generate_synthetic_sds.py")

    with open(pdf_path, "rb") as f:
        resp = client.post("/screen", files={"file": ("doc-01.pdf", f.read(), "application/pdf")})
    assert resp.status_code == 202
    product_id = resp.json()["product_id"]

    for _ in range(30):
        status_resp = client.get(f"/product/{product_id}/status")
        assert status_resp.status_code == 200
        status = status_resp.json()["status"]
        if status in ("complete", "needs_review", "error"):
            break
        time.sleep(1)

    assert status in ("complete", "needs_review")
    report = status_resp.json()["report"]
    assert report is not None
    assert len(report["substance_verdicts"]) > 0
