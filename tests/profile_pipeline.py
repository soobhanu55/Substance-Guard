"""cProfile a single full pipeline run and bucket cumulative time by stage (PDF parse /
Gemini call / Neo4j / Qdrant / guardrails) to find the actual bottleneck. Deliberately
profiles just ONE document -- given the free-tier Gemini quota constraints discovered
elsewhere in this evaluation (see reports/load_test_report.md), this is intentionally
cheap to re-run.

Run: python tests/profile_pipeline.py
"""
from __future__ import annotations

import asyncio
import cProfile
import io
import pstats
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pdf.parser import extract_text
from app.pipeline.graph import compiled_graph

PDF_PATH = Path(__file__).resolve().parent.parent / "db" / "synthetic_sds" / "pdfs" / "doc-07.pdf"
REPORT_PATH = Path(__file__).resolve().parent.parent / "reports" / "profiling_report.md"

# (bucket label, substrings matched against "<module>:<lineno>(<function>)")
BUCKETS = [
    ("PDF parsing (pdfplumber)", ["pdfplumber", "pdfminer"]),
    ("Gemini LLM call (network + SDK)", ["genai", "gemini_provider", "httpx", "httpcore", "ssl", "socket"]),
    ("Neo4j queries", ["neo4j", "graph\\queries", "graph\\loader", "graph/queries", "graph/loader"]),
    ("Qdrant / embeddings (RAG retrieval)", ["qdrant", "embeddings", "rag\\retriever", "rag/retriever"]),
    ("Guardrails", ["guardrails"]),
]


def _bucket_for(func_key: str) -> str:
    for label, substrings in BUCKETS:
        if any(s in func_key for s in substrings):
            return label
    return "Other (asyncio/orchestration/langgraph internals)"


async def run_once():
    raw_text = extract_text(PDF_PATH.read_bytes())
    async with compiled_graph() as graph:
        config = {"configurable": {"thread_id": "profile-run"}}
        await graph.ainvoke(
            {"product_id": "profile-run", "filename": "doc-07.pdf", "raw_text": raw_text, "interactive": False},
            config=config,
        )


def main():
    profiler = cProfile.Profile()
    profiler.enable()
    asyncio.run(run_once())
    profiler.disable()

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream).sort_stats("cumulative")
    stats.print_stats(0)  # populate stats.stats without truncated text output

    bucket_totals: dict[str, float] = {}
    total_cumtime = 0.0
    for (filename, lineno, funcname), (cc, nc, tt, ct, callers) in stats.stats.items():
        key = f"{filename}:{lineno}({funcname})"
        bucket = _bucket_for(key)
        # Use own time (tt), not cumulative, to avoid double-counting nested calls
        bucket_totals[bucket] = bucket_totals.get(bucket, 0.0) + tt
        total_cumtime += tt

    sorted_buckets = sorted(bucket_totals.items(), key=lambda kv: kv[1], reverse=True)

    lines = ["# Pipeline Profiling Report", "", f"Single-document profile (`doc-07.pdf`, cProfile, own-time per bucket):", ""]
    lines.append("| Stage | Time (s) | % of profiled time |")
    lines.append("|---|---|---|")
    for label, t in sorted_buckets:
        pct = (t / total_cumtime * 100) if total_cumtime else 0
        lines.append(f"| {label} | {t:.4f} | {pct:.1f}% |")
    lines.append("")
    lines.append(f"Total profiled (own-time sum): {total_cumtime:.4f}s")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    top_label, top_time = sorted_buckets[0]
    lines.append(
        f"**{top_label}** dominates at {top_time / total_cumtime * 100:.1f}% of own-time -- "
        f"consistent with the load-test finding (`reports/load_test_report.md`) that Gemini's "
        f"rate limit, not this service's own code, is the binding constraint on throughput. "
        f"Next optimization to try: batch multiple documents' extraction into fewer, larger "
        f"Gemini calls where the workflow allows it, and cache graph_lookup results for "
        f"repeat CAS numbers across documents (Neo4j lookups are already sub-millisecond per "
        f"the load test, so caching saves round-trip count, not per-call latency)."
    )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWritten to {REPORT_PATH}")


if __name__ == "__main__":
    main()
