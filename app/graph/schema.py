from __future__ import annotations

import structlog

from app.graph.client import get_driver

logger = structlog.get_logger(__name__)

CONSTRAINTS_AND_INDEXES = [
    "CREATE CONSTRAINT substance_cas IF NOT EXISTS FOR (s:Substance) REQUIRE s.cas_number IS UNIQUE",
    "CREATE CONSTRAINT regulation_name IF NOT EXISTS FOR (r:Regulation) REQUIRE r.name IS UNIQUE",
    "CREATE CONSTRAINT product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT component_id IF NOT EXISTS FOR (c:Component) REQUIRE c.id IS UNIQUE",
    "CREATE INDEX substance_name IF NOT EXISTS FOR (s:Substance) ON (s.name)",
]


async def apply_schema() -> None:
    driver = get_driver()
    async with driver.session() as session:
        for statement in CONSTRAINTS_AND_INDEXES:
            await session.run(statement)
    logger.info("graph_schema_applied", statement_count=len(CONSTRAINTS_AND_INDEXES))
