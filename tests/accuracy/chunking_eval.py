"""Head-to-head eval of the clause-based vs fixed-window chunker, run against the live
Qdrant collections populated by app.rag.ingest.ingest_regulation_corpus().

Two metrics, deliberately not one, because the two chunkers are not comparable on a
single number:
  - exact_clause_match@3: does a top-3 hit carry the *exact* expected clause/article id
    as a citation? Only the clause-based chunker CAN score here (fixed-window chunks
    have no clause_id) -- this is the citation-precision property the verdict node
    needs (it must cite "Article 33", not "somewhere in the SVHC document").
  - correct_regulation_recall@1: does the top-1 hit at least come from the right source
    regulation? This is the retrieval-relevance floor both strategies should clear.

Run: python tests/accuracy/chunking_eval.py  (requires Qdrant + a real Gemini key; run
app.rag.ingest.ingest_regulation_corpus() first if the collections are empty)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.config import get_settings
from app.rag.retriever import retrieve

EVAL_SET = [
    {"question": "What concentration threshold triggers the SVHC notification obligation to ECHA?",
     "regulation_name": "REACH_SVHC", "expected_clause": "Article 33"},
    {"question": "What is a homogeneous material under RoHS?",
     "regulation_name": "ROHS_ANNEX_II", "expected_clause": "Annex II"},
    {"question": "What is the maximum lead concentration allowed under RoHS?",
     "regulation_name": "ROHS_ANNEX_II", "expected_clause": "Annex II"},
    {"question": "When did ECHA's Risk Assessment Committee adopt its opinion on the PFAS restriction?",
     "regulation_name": "PFAS_RESTRICTION_DRAFT", "expected_clause": "Clause 2"},
    {"question": "What are the three PFAS concentration thresholds being proposed?",
     "regulation_name": "PFAS_RESTRICTION_DRAFT", "expected_clause": "Clause 3"},
    {"question": "Does the new PFAS restriction affect surface coatings?",
     "regulation_name": "PFAS_RESTRICTION_DRAFT", "expected_clause": "Clause 5"},
    {"question": "What substances were added to RoHS Annex II by the 2015 amendment?",
     "regulation_name": "ROHS_ANNEX_II", "expected_clause": "Annex II"},
    {"question": "What triggers notification of a substance to the ECHA SCIP database?",
     "regulation_name": "REACH_SVHC", "expected_clause": "Article 7"},
    {"question": "How does the PFAS restriction define PFAS structurally?",
     "regulation_name": "PFAS_RESTRICTION_DRAFT", "expected_clause": "Clause 1"},
    {"question": "What derogation options exist under the draft PFAS restriction?",
     "regulation_name": "PFAS_RESTRICTION_DRAFT", "expected_clause": "Clause 4"},
    {"question": "What criteria make a substance a Substance of Very High Concern?",
     "regulation_name": "REACH_SVHC", "expected_clause": "Article 57"},
    {"question": "What is the RoHS concentration threshold for cadmium?",
     "regulation_name": "ROHS_ANNEX_II", "expected_clause": "Annex II"},
]


async def run_eval(collection: str, strategy_name: str) -> dict:
    exact_hits, top1_regulation_hits, rows = 0, 0, []
    for item in EVAL_SET:
        results = await retrieve(item["question"], top_k=3, collection=collection)
        clause_ids = [r.clause_id for r in results if r.clause_id]
        exact = any(item["expected_clause"] in (cid or "") for cid in clause_ids)
        top1_reg_ok = bool(results) and results[0].regulation_name == item["regulation_name"]
        exact_hits += int(exact)
        top1_regulation_hits += int(top1_reg_ok)
        rows.append({
            "question": item["question"], "expected_clause": item["expected_clause"],
            "retrieved_clause_ids": clause_ids, "exact_clause_match": exact,
            "top1_regulation_correct": top1_reg_ok,
        })
    n = len(EVAL_SET)
    return {
        "strategy": strategy_name,
        "exact_clause_match_at_3": exact_hits / n,
        "correct_regulation_recall_at_1": top1_regulation_hits / n,
        "n_questions": n,
        "rows": rows,
    }


async def main():
    settings = get_settings()
    clause_report = await run_eval(settings.qdrant_collection_clauses, "clause_based")
    fixed_report = await run_eval(settings.qdrant_collection_fixed, "fixed_window")
    report = {"clause_based": clause_report, "fixed_window": fixed_report}

    out_path = Path(__file__).resolve().parent.parent.parent / "reports" / "chunking_eval_report.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"clause_based:  exact_clause_match@3={clause_report['exact_clause_match_at_3']:.2f}  "
          f"correct_regulation_recall@1={clause_report['correct_regulation_recall_at_1']:.2f}")
    print(f"fixed_window:  exact_clause_match@3={fixed_report['exact_clause_match_at_3']:.2f}  "
          f"correct_regulation_recall@1={fixed_report['correct_regulation_recall_at_1']:.2f}")
    print(f"\nreport written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
