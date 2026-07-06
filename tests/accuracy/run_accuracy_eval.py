"""Runs the full 6-node pipeline over all 26 synthetic SDS/test-report PDFs and scores
extraction accuracy + verdict accuracy against db/synthetic_sds/ground_truth.json.
Requires the live stack (Neo4j + Qdrant + a real Gemini key) -- run with
`docker compose up -d neo4j qdrant` (or the full stack) first.

Run: python tests/accuracy/run_accuracy_eval.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.pdf.parser import extract_text
from app.pipeline.graph import compiled_graph

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PDFS_DIR = PROJECT_ROOT / "db" / "synthetic_sds" / "pdfs"
GROUND_TRUTH_PATH = PROJECT_ROOT / "db" / "synthetic_sds" / "ground_truth.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "accuracy_report.json"


def _extraction_matches(expected: dict, extracted_list: list[dict]) -> dict | None:
    """Finds the extracted substance (if any) corresponding to one expected ground-truth
    component -- matched by CAS number when the ground truth has one, else by
    component name (each synthetic doc has at most one substance per component)."""
    for extracted in extracted_list:
        if expected["cas_number"] and extracted.get("cas_number") == expected["cas_number"]:
            return extracted
    for extracted in extracted_list:
        if extracted.get("component_name") == expected["component_name"]:
            return extracted
    return None


def _extraction_correct(expected: dict, extracted: dict | None) -> bool:
    if extracted is None:
        return False
    if expected["cas_number"] != extracted.get("cas_number"):
        return False
    if abs(float(extracted.get("concentration", -1)) - expected["concentration"]) > 1e-6:
        return False
    if extracted.get("unit") != expected["unit"]:
        return False
    return True


async def run_one_document(doc_id: str, doc: dict) -> dict:
    pdf_path = PDFS_DIR / f"{doc_id}.pdf"
    raw_text = extract_text(pdf_path.read_bytes())

    async with compiled_graph() as graph:
        config = {"configurable": {"thread_id": f"eval-{doc_id}"}}
        result = await graph.ainvoke(
            {"product_id": f"eval-{doc_id}", "filename": f"{doc_id}.pdf", "raw_text": raw_text, "interactive": False},
            config=config,
        )

    extracted_list = result.get("extracted_substances", [])
    verdicts = result.get("verdicts", [])

    component_results = []
    for expected in doc["components"]:
        extracted = _extraction_matches(expected, extracted_list)
        extraction_ok = _extraction_correct(expected, extracted)

        verdict = next((v for v in verdicts if v["component_name"] == expected["component_name"]), None)
        actual_status = verdict["status"] if verdict else None
        verdict_ok = actual_status == expected["expected_status"]

        component_results.append({
            "component_name": expected["component_name"],
            "expected_substance": expected["substance_name"],
            "extraction_correct": extraction_ok,
            "expected_status": expected["expected_status"],
            "actual_status": actual_status,
            "verdict_correct": verdict_ok,
        })
    return {"doc_id": doc_id, "case": doc["case"], "components": component_results}


async def main() -> None:
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    all_results = []
    failed_docs = []
    for doc_id, doc in ground_truth.items():
        print(f"Running {doc_id} ({doc['case']})...")
        try:
            all_results.append(await run_one_document(doc_id, doc))
        except Exception as exc:  # noqa: BLE001 -- one flaky call shouldn't abort the whole eval run
            print(f"  FAILED: {exc}")
            failed_docs.append({"doc_id": doc_id, "error": str(exc)})

    if not all_results:
        print("All documents failed -- nothing to report.")
        return

    total_components = sum(len(r["components"]) for r in all_results)
    extraction_correct = sum(c["extraction_correct"] for r in all_results for c in r["components"])
    verdict_correct = sum(c["verdict_correct"] for r in all_results for c in r["components"])

    expected_review = [c for r in all_results for c in r["components"] if c["expected_status"] == "NEEDS_REVIEW"]
    expected_decided = [c for r in all_results for c in r["components"] if c["expected_status"] != "NEEDS_REVIEW"]
    correctly_routed_to_review = sum(c["actual_status"] == "NEEDS_REVIEW" for c in expected_review)
    correctly_auto_decided = sum(c["actual_status"] == c["expected_status"] for c in expected_decided)

    summary = {
        "total_documents": len(all_results),
        "failed_documents": failed_docs,
        "total_substance_components": total_components,
        "extraction_accuracy": extraction_correct / total_components,
        "verdict_accuracy": verdict_correct / total_components,
        "expected_needs_review_count": len(expected_review),
        "correctly_routed_to_review": correctly_routed_to_review,
        "review_routing_recall": correctly_routed_to_review / len(expected_review) if expected_review else None,
        "expected_auto_decided_count": len(expected_decided),
        "correctly_auto_decided": correctly_auto_decided,
        "auto_decide_accuracy": correctly_auto_decided / len(expected_decided) if expected_decided else None,
        "by_case": {},
        "results": all_results,
    }

    by_case: dict[str, dict] = {}
    for r in all_results:
        c = by_case.setdefault(r["case"], {"docs": 0, "components": 0, "extraction_correct": 0, "verdict_correct": 0})
        c["docs"] += 1
        for comp in r["components"]:
            c["components"] += 1
            c["extraction_correct"] += int(comp["extraction_correct"])
            c["verdict_correct"] += int(comp["verdict_correct"])
    summary["by_case"] = by_case

    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    def _fmt(v):
        return f"{v:.1%}" if v is not None else "n/a"

    print(f"\nExtraction accuracy: {_fmt(summary['extraction_accuracy'])}")
    print(f"Verdict accuracy:    {_fmt(summary['verdict_accuracy'])}")
    print(f"Review routing recall: {_fmt(summary['review_routing_recall'])} "
          f"({correctly_routed_to_review}/{len(expected_review)})")
    print(f"Auto-decide accuracy:  {_fmt(summary['auto_decide_accuracy'])} "
          f"({correctly_auto_decided}/{len(expected_decided)})")
    if failed_docs:
        print(f"\n{len(failed_docs)} document(s) failed (see reports/accuracy_report.json 'failed_documents'):")
        for f in failed_docs:
            print(f"  {f['doc_id']}: {f['error'][:120]}")
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
