from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.graph.client import get_driver

MAX_BOM_DEPTH = 6  # bound on nested-component traversal depth


# --- write path: ingestion ---

async def upsert_product(product_id: str, name: str, manufacturer: str | None = None) -> None:
    driver = get_driver()
    async with driver.session() as session:
        await session.run(
            "MERGE (p:Product {id: $id}) SET p.name = $name, p.manufacturer = $manufacturer",
            id=product_id, name=name, manufacturer=manufacturer or "",
        )


async def upsert_component(component_id: str, name: str, parent_product_id: str | None = None,
                            parent_component_id: str | None = None) -> None:
    driver = get_driver()
    async with driver.session() as session:
        await session.run("MERGE (c:Component {id: $id}) SET c.name = $name", id=component_id, name=name)
        if parent_product_id:
            await session.run(
                "MATCH (p:Product {id: $pid}), (c:Component {id: $cid}) MERGE (p)-[:CONTAINS]->(c)",
                pid=parent_product_id, cid=component_id,
            )
        if parent_component_id:
            await session.run(
                "MATCH (parent:Component {id: $pid}), (c:Component {id: $cid}) MERGE (parent)-[:CONTAINS]->(c)",
                pid=parent_component_id, cid=component_id,
            )


async def record_substance_in_component(
    component_id: str, cas_number: str, concentration_pct: float, source_doc_id: str,
) -> None:
    driver = get_driver()
    async with driver.session() as session:
        await session.run(
            """
            MATCH (c:Component {id: $cid})
            MERGE (s:Substance {cas_number: $cas})
            ON CREATE SET s.name = coalesce(s.name, 'Unregistered substance ' + $cas), s.pfas_structural_flag = false
            MERGE (c)-[rel:CONTAINS_SUBSTANCE]->(s)
            SET rel.concentration_pct = $conc, rel.source_doc_id = $doc_id, rel.extracted_at = $ts
            """,
            cid=component_id, cas=cas_number, conc=concentration_pct,
            doc_id=source_doc_id, ts=datetime.now(timezone.utc).isoformat(),
        )


# --- read path: single-substance lookup (pipeline Node 2 + GET /substance/{cas}/regulations) ---

async def get_substance_regulations(cas_number: str) -> dict[str, Any] | None:
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (s:Substance {cas_number: $cas})
            OPTIONAL MATCH (s)-[:REGULATED_BY]->(r:Regulation)
            OPTIONAL MATCH (s)-[:HAS_THRESHOLD]->(t:Threshold)-[:BELONGS_TO]->(r2:Regulation)
            RETURN s.name AS name, s.pfas_structural_flag AS pfas_flag,
                   collect(DISTINCT {name: r.name, legal_ref: r.legal_ref, status: r.status}) AS regulations,
                   collect(DISTINCT {basis: t.basis, value: t.value, unit: t.unit, regulation: r2.name}) AS thresholds
            """,
            cas=cas_number,
        )
        record = await result.single()
        if record is None or record["name"] is None:
            return None
        regulations = [r for r in record["regulations"] if r["name"] is not None]
        thresholds = [t for t in record["thresholds"] if t["basis"] is not None]
        return {
            "cas_number": cas_number,
            "name": record["name"],
            "pfas_structural_flag": record["pfas_flag"],
            "regulations": regulations,
            "thresholds": thresholds,
        }


async def find_substance_by_name_fuzzy(name: str) -> dict[str, Any] | None:
    """Fallback when extraction produced no CAS number or the CAS didn't match.
    Deliberately conservative (CONTAINS, case-insensitive) -- a fuzzy hit is a signal
    for human review, never treated as confirmed by the guardrail layer."""
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (s:Substance)
            WHERE toLower(s.name) CONTAINS toLower($name) OR toLower($name) CONTAINS toLower(s.name)
            RETURN s.cas_number AS cas_number, s.name AS name
            LIMIT 5
            """,
            name=name,
        )
        records = [r async for r in result]
        if not records:
            return None
        return {"cas_number": records[0]["cas_number"], "name": records[0]["name"], "candidate_count": len(records)}


# --- demonstrative multi-hop queries (README + graph/queries.py callers) ---

async def products_containing_regulation(regulation_name: str) -> list[dict[str, Any]]:
    """Query 1: blast radius of a newly-restricted substance -- every product that
    contains it anywhere in its (arbitrarily nested) component tree."""
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH (p:Product)-[:CONTAINS*1..{MAX_BOM_DEPTH}]->(:Component)-[:CONTAINS_SUBSTANCE]->(s:Substance)
                  -[:REGULATED_BY]->(r:Regulation {{name: $reg}})
            RETURN DISTINCT p.id AS product_id, p.name AS product_name, collect(DISTINCT s.name) AS substances
            """,
            reg=regulation_name,
        )
        return [dict(r) async for r in result]


async def product_threshold_exceedances(product_id: str) -> list[dict[str, Any]]:
    """Query 2: every substance in a specific product's component tree whose measured
    concentration exceeds its regulatory threshold."""
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH (p:Product {{id: $pid}})-[:CONTAINS*1..{MAX_BOM_DEPTH}]->(c:Component)
                  -[rel:CONTAINS_SUBSTANCE]->(s:Substance)-[:HAS_THRESHOLD]->(t:Threshold)-[:BELONGS_TO]->(r:Regulation)
            WHERE (t.unit = 'pct' AND rel.concentration_pct > t.value)
               OR (t.unit = 'ppm' AND rel.concentration_pct * 10000 > t.value)
               OR (t.unit = 'ppb' AND rel.concentration_pct * 10000000 > t.value)
            RETURN c.id AS component_id, c.name AS component_name, s.cas_number AS cas_number, s.name AS substance_name,
                   rel.concentration_pct AS concentration_pct, t.value AS threshold_value, t.unit AS threshold_unit,
                   r.name AS regulation_name
            """,
            pid=product_id,
        )
        return [dict(r) async for r in result]


async def products_containing_pfas_anywhere() -> list[dict[str, Any]]:
    """Query 3: the multi-hop query that justifies the graph. 'Which products contain
    ANY PFAS substance through ANY component, at ANY nesting depth' -- either named on
    the draft restriction list or matching the structural definition heuristic.

    Why this is awkward in SQL: a bill-of-materials with unknown, variable nesting depth
    (product -> assembly -> sub-assembly -> part -> substance) requires either a
    recursive CTE that re-checks the substance-flag join condition at every recursion
    level, or a UNION of N fixed-depth joins guessing at max depth. In Cypher it's a
    single variable-length pattern match.
    """
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH (p:Product)-[:CONTAINS*1..{MAX_BOM_DEPTH}]->(:Component)-[:CONTAINS_SUBSTANCE]->(s:Substance)
            WHERE s.pfas_structural_flag = true
               OR (s)-[:REGULATED_BY]->(:Regulation {{name: 'PFAS_RESTRICTION_DRAFT'}})
            RETURN DISTINCT p.id AS product_id, p.name AS product_name, collect(DISTINCT s.name) AS pfas_substances
            """
        )
        return [dict(r) async for r in result]


EQUIVALENT_RECURSIVE_SQL = """
-- Equivalent in a relational schema (products, components, component_substances,
-- component_edges(parent_component_id, child_component_id)) requires a recursive CTE:
WITH RECURSIVE bom_tree(product_id, component_id, depth) AS (
    SELECT p.id, pc.component_id, 1
    FROM products p JOIN product_components pc ON pc.product_id = p.id
    UNION ALL
    SELECT bt.product_id, ce.child_component_id, bt.depth + 1
    FROM bom_tree bt
    JOIN component_edges ce ON ce.parent_component_id = bt.component_id
    WHERE bt.depth < 6  -- must hard-code a depth bound; Cypher's *1..6 is declarative
)
SELECT DISTINCT bt.product_id
FROM bom_tree bt
JOIN component_substances cs ON cs.component_id = bt.component_id
JOIN substances s ON s.cas_number = cs.cas_number
WHERE s.pfas_structural_flag = true OR s.cas_number IN (SELECT cas_number FROM pfas_restriction_list);
-- Every added BOM level (new component type, deeper sub-assembly) requires re-verifying
-- this recursive CTE still terminates and performs -- and most application ORMs cannot
-- express recursive CTEs at all without dropping to raw SQL.
"""
