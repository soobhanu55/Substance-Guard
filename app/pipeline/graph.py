from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, StateGraph

from app.config import get_settings
from app.pipeline.nodes.graph_lookup import graph_lookup_node
from app.pipeline.nodes.human_review import human_review_node
from app.pipeline.nodes.intake import intake_node
from app.pipeline.nodes.rag_retrieval import rag_retrieval_node
from app.pipeline.nodes.report import report_node
from app.pipeline.nodes.verdict import verdict_node
from app.pipeline.state import PipelineState


def build_graph():
    builder = StateGraph(PipelineState)
    builder.add_node("intake", intake_node)
    builder.add_node("graph_lookup", graph_lookup_node)
    builder.add_node("rag_retrieval", rag_retrieval_node)
    builder.add_node("verdict", verdict_node)
    builder.add_node("generate_report", report_node)
    builder.add_node("human_review", human_review_node)

    builder.set_entry_point("intake")
    builder.add_edge("intake", "graph_lookup")
    builder.add_edge("graph_lookup", "rag_retrieval")
    builder.add_edge("rag_retrieval", "verdict")
    builder.add_edge("verdict", "generate_report")
    builder.add_edge("generate_report", "human_review")
    builder.add_edge("human_review", END)
    return builder


@asynccontextmanager
async def compiled_graph():
    """Compiles the graph with a SQLite checkpointer so Node 6's interrupt() genuinely
    suspends and can be resumed later (e.g. across FastAPI requests) via
    graph.ainvoke(Command(resume=...), config={"configurable": {"thread_id": product_id}})."""
    settings = get_settings()
    Path(settings.checkpoint_db_path).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(settings.checkpoint_db_path) as saver:
        yield build_graph().compile(checkpointer=saver)
