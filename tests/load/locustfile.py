"""Locust load test against the live FastAPI service (docker compose up first).

Two user classes, run separately (see reports/load_test_report.md for why):
  - GraphLookupUser: hits the Neo4j-backed GET endpoints, no LLM involved -- this is
    where real throughput/latency numbers under load are meaningful.
  - ScreenUser: hits POST /screen, which makes a real Gemini call per request. This
    project's own accuracy/safety evals burned most of today's free-tier quota across
    three different models (see reports/accuracy_report.json and safety_report.json),
    so the /screen load test in reports/load_test_report.md was deliberately run at a
    small, quota-conscious volume rather than the originally-planned full volume --
    documented there as a real, measured operational constraint, not an assumption.

Run (graph-only, full volume):
    locust -f tests/load/locustfile.py --host=http://localhost:8000 GraphLookupUser \
        --headless -u 20 -r 5 -t 60s --csv=reports/load_graph

Run (screen, capped volume):
    locust -f tests/load/locustfile.py --host=http://localhost:8000 ScreenUser \
        --headless -u 3 -r 1 -t 40s --csv=reports/load_screen
"""
import random
from pathlib import Path

from locust import HttpUser, between, task

SAMPLE_CAS_NUMBERS = [
    "335-67-1", "1763-23-1", "7439-92-1", "7440-43-9", "117-81-7", "84-74-2",
    "80-05-7", "10043-35-3", "355-46-4", "375-73-5",
]

PDF_DIR = Path(__file__).resolve().parent.parent.parent / "db" / "synthetic_sds" / "pdfs"
_COMPLIANT_PDFS = [PDF_DIR / f"doc-{i:02d}.pdf" for i in range(1, 7)]  # clearly_compliant docs, cheap/short


class GraphLookupUser(HttpUser):
    """Pure-graph endpoints: no LLM call, safe to run at real load-test volume."""
    wait_time = between(0.1, 0.5)

    @task(3)
    def substance_regulations(self):
        cas = random.choice(SAMPLE_CAS_NUMBERS)
        self.client.get(f"/substance/{cas}/regulations", name="/substance/[cas]/regulations")

    @task(1)
    def health(self):
        self.client.get("/health")


class ScreenUser(HttpUser):
    """Real Gemini call per request -- run at a small, capped volume (see module
    docstring for why this isn't the originally-planned full-volume run)."""
    wait_time = between(1, 2)

    @task
    def screen_document(self):
        pdf_path = random.choice(_COMPLIANT_PDFS)
        with open(pdf_path, "rb") as f:
            self.client.post("/screen", files={"file": (pdf_path.name, f.read(), "application/pdf")},
                              name="/screen")
