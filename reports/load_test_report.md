# Load Test Report

Run against the live `docker compose` stack (`gemini-3.1-flash-lite`, see the model-selection
note below) on 2026-07-05. Raw Locust CSVs: `load_graph_stats.csv`, `load_screen_stats.csv`.

## 1. Graph-backed endpoints (`/health`, `/substance/{cas}/regulations`) -- full volume

30 concurrent users, ramped at 10/s, 45s run, no LLM involved (pure Neo4j read path):

| Endpoint | Requests | Failures | p50 | p95 | p99 | Throughput |
|---|---|---|---|---|---|---|
| `/health` | 1,099 | 0 | 3ms | 5ms | 15ms | ~25 req/s |
| `/substance/{cas}/regulations` | 3,086 | 0 | 6ms | 9ms | 12ms | ~71 req/s |
| **Aggregated** | **4,185** | **0 (0.00%)** | **5ms** | **9ms** | **12ms** | **~96 req/s (~5,760 RPM)** |

Zero failures, single-digit-millisecond latency at this volume -- the Neo4j lookup path
(a single indexed match + two optional relationship traversals, see
`app/graph/queries.get_substance_regulations`) is not the bottleneck anywhere in this system.

## 2. `POST /screen` -- capped volume, and why

`/screen` returns `202 Accepted` immediately after PDF parsing and enqueues the actual
6-node pipeline (including the real Gemini extraction call) as a FastAPI background task
-- so the HTTP-level load test below measures **enqueue latency**, not pipeline
completion. 3 concurrent users, 40s run:

| Endpoint | Requests | HTTP failures | p50 | p95 | p99 | Throughput |
|---|---|---|---|---|---|---|
| `/screen` (enqueue only) | 78 | 0 (0.00%) | 72ms | 130ms | 240ms | ~2 req/s (~120 RPM) |

That 0% HTTP failure rate is misleading on its own -- it only reflects the upload+enqueue
step. Checking actual pipeline completion (`data/product_status.json`) for those same 78
requests tells the real story:

| Outcome | Count | % |
|---|---|---|
| Completed successfully | 16 | 20.5% |
| Failed (`429 RESOURCE_EXHAUSTED` from Gemini) | 62 | 79.5% |

**This is the finding the project plan predicted and it held up under measurement:
`/screen`'s achieved throughput is capped by the LLM provider's rate limit, not by this
service's own capacity.** The Neo4j/FastAPI path handled 96 req/s above with zero
failures; the same server handling 78 background pipeline runs in the same window saw
79.5% of them rejected upstream by Gemini.

### Model-selection note (a real constraint discovered while building this report)

The original plan called for a full-volume `/screen` load test on `gemini-2.5-flash`
(the model used everywhere else in development). Running this project's own accuracy and
adversarial-safety evals in the same session exhausted that model's free-tier daily quota
(20 requests/day) and then `gemini-2.5-flash-lite`'s (also 20/day) before load testing even
started. `gemini-3.1-flash-lite` had a fresh quota pool and was used for the 26-document
accuracy suite, the adversarial safety suite, and this load test -- but its per-minute
quota (10 req/min observed) is still the direct cause of the 79.5% background-completion
failure rate above at just 3 concurrent users. A production deployment would need a paid
tier with a request-per-minute quota sized to actual expected concurrency; this number is
exactly the kind of capacity-planning input that quota ceiling should inform.

## 3. Bottleneck identification

Combining this with `reports/profiling_report.md`: the LLM call is the dominant cost in
wall-clock time per document (see profiling breakdown), and now the load test shows it is
*also* the binding constraint on throughput under concurrency -- more so than raw latency
would suggest, because of the provider's per-minute rate limit rather than per-call
latency. The Neo4j and Qdrant lookups, run concurrently at 30 users above, contribute
single-digit milliseconds and did not fail once.
