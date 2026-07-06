# Pipeline Profiling Report

Single-document profile (`doc-07.pdf`, cProfile, own-time per bucket):

| Stage | Time (s) | % of profiled time |
|---|---|---|
| Gemini LLM call (network + SDK) | 3.2712 | 60.2% |
| Other (asyncio/orchestration/langgraph internals) | 2.0786 | 38.3% |
| PDF parsing (pdfplumber) | 0.0794 | 1.5% |
| Neo4j queries | 0.0036 | 0.1% |
| Qdrant / embeddings (RAG retrieval) | 0.0011 | 0.0% |
| Guardrails | 0.0001 | 0.0% |

Total profiled (own-time sum): 5.4339s

## Interpretation

**Gemini LLM call (network + SDK)** dominates at 60.2% of own-time -- consistent with the load-test finding (`reports/load_test_report.md`) that Gemini's rate limit, not this service's own code, is the binding constraint on throughput. Next optimization to try: batch multiple documents' extraction into fewer, larger Gemini calls where the workflow allows it, and cache graph_lookup results for repeat CAS numbers across documents (Neo4j lookups are already sub-millisecond per the load test, so caching saves round-trip count, not per-call latency).