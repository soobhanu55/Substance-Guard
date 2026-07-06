from __future__ import annotations

import json
import re
from pathlib import Path

import structlog

from app.graph.client import get_driver

logger = structlog.get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "db" / "regulatory_data"

_PFAS_NAME_PATTERNS = [
    r"perfluoro", r"polyfluoro", r"fluorotelomer", r"\bfts\b", r"ftoh", r"fosa",
    r"fosaa", r"fose", r"pfoa", r"pfos", r"pfas", r"genx", r"adona",
]
_PFAS_NAME_RE = re.compile("|".join(_PFAS_NAME_PATTERNS), re.IGNORECASE)


def looks_like_pfas(name: str) -> bool:
    """Structural-definition heuristic: catches PFAS substances that are not in the
    named 40-entry list (real ECHA restriction covers ~14,000 substances by structural
    definition, not enumeration -- see db/regulatory_data/pfas_restriction.json _meta)."""
    return bool(_PFAS_NAME_RE.search(name))


def _load_json(filename: str) -> dict:
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


async def load_regulatory_data() -> dict:
    """Idempotent: uses MERGE throughout, safe to re-run (e.g. on every container start)."""
    svhc = _load_json("svhc_candidate_list.json")
    rohs = _load_json("rohs_annex_ii.json")
    pfas = _load_json("pfas_restriction.json")

    driver = get_driver()
    counts = {"regulations": 0, "thresholds": 0, "substances": 0}

    async with driver.session() as session:
        # --- Regulations ---
        await session.run(
            """
            MERGE (r:Regulation {name: 'REACH_SVHC'})
            SET r.legal_ref = $legal_ref, r.status = 'in_force', r.description = $desc
            """,
            legal_ref=svhc["_meta"]["legal_ref"],
            desc="ECHA Candidate List of Substances of Very High Concern (Article 59)",
        )
        await session.run(
            """
            MERGE (r:Regulation {name: 'ROHS_ANNEX_II'})
            SET r.legal_ref = $legal_ref, r.status = 'in_force', r.description = $desc
            """,
            legal_ref=rohs["_meta"]["legal_ref"],
            desc="RoHS Directive 2011/65/EU Annex II restricted substances",
        )
        await session.run(
            """
            MERGE (r:Regulation {name: 'PFAS_RESTRICTION_DRAFT'})
            SET r.legal_ref = $legal_ref, r.status = $status, r.description = $desc
            """,
            legal_ref=pfas["_meta"]["regulation_status"]["legal_ref"],
            status=pfas["_meta"]["regulation_status"]["status_as_of"],
            desc="Draft REACH Annex XVII restriction on per- and polyfluoroalkyl substances",
        )
        counts["regulations"] = 3

        # --- SVHC: one shared threshold (0.1% notification trigger) ---
        await session.run(
            """
            MATCH (r:Regulation {name: 'REACH_SVHC'})
            MERGE (t:Threshold {basis: 'svhc_notification', regulation_name: 'REACH_SVHC'})
            SET t.value = $value, t.unit = 'pct'
            MERGE (t)-[:BELONGS_TO]->(r)
            """,
            value=svhc["_meta"]["threshold_pct"],
        )
        counts["thresholds"] += 1

        for sub in svhc["substances"]:
            await session.run(
                """
                MERGE (s:Substance {cas_number: $cas})
                SET s.name = coalesce(s.name, $name), s.pfas_structural_flag = coalesce(s.pfas_structural_flag, false)
                WITH s
                MATCH (r:Regulation {name: 'REACH_SVHC'})
                MATCH (t:Threshold {basis: 'svhc_notification', regulation_name: 'REACH_SVHC'})
                MERGE (s)-[:REGULATED_BY]->(r)
                MERGE (s)-[:HAS_THRESHOLD]->(t)
                """,
                cas=sub["cas_number"],
                name=sub["name"],
            )
            counts["substances"] += 1

        # --- RoHS: per-substance threshold (0.1% standard, 0.01% cadmium) ---
        for sub in rohs["substances"]:
            await session.run(
                """
                MERGE (t:Threshold {basis: 'rohs_homogeneous_material', regulation_name: 'ROHS_ANNEX_II', value: $value})
                SET t.unit = 'pct'
                WITH t
                MATCH (r:Regulation {name: 'ROHS_ANNEX_II'})
                MERGE (t)-[:BELONGS_TO]->(r)
                """,
                value=sub["threshold_pct"],
            )
            await session.run(
                """
                MERGE (s:Substance {cas_number: $cas})
                SET s.name = coalesce(s.name, $name), s.pfas_structural_flag = coalesce(s.pfas_structural_flag, false)
                WITH s
                MATCH (r:Regulation {name: 'ROHS_ANNEX_II'})
                MATCH (t:Threshold {basis: 'rohs_homogeneous_material', regulation_name: 'ROHS_ANNEX_II', value: $value})
                MERGE (s)-[:REGULATED_BY]->(r)
                MERGE (s)-[:HAS_THRESHOLD]->(t)
                """,
                cas=sub["cas_number"],
                name=sub["name"],
                value=sub["threshold_pct"],
            )
            counts["substances"] += 1
            counts["thresholds"] += 1

        # --- PFAS: three regulation-level thresholds + per-substance individual link ---
        for th in pfas["_meta"]["proposed_thresholds"]:
            value = th.get("value_ppb", th.get("value_ppm"))
            unit = "ppb" if "value_ppb" in th else "ppm"
            await session.run(
                """
                MERGE (t:Threshold {basis: $basis, regulation_name: 'PFAS_RESTRICTION_DRAFT'})
                SET t.value = $value, t.unit = $unit, t.method = $method
                WITH t
                MATCH (r:Regulation {name: 'PFAS_RESTRICTION_DRAFT'})
                MERGE (t)-[:BELONGS_TO]->(r)
                """,
                basis=th["basis"],
                value=value,
                unit=unit,
                method=th["method"],
            )
            counts["thresholds"] += 1

        for sub in pfas["substances"]:
            await session.run(
                """
                MERGE (s:Substance {cas_number: $cas})
                SET s.name = coalesce(s.name, $name), s.pfas_structural_flag = true
                WITH s
                MATCH (r:Regulation {name: 'PFAS_RESTRICTION_DRAFT'})
                MATCH (t:Threshold {basis: 'individual_pfas', regulation_name: 'PFAS_RESTRICTION_DRAFT'})
                MERGE (s)-[:REGULATED_BY]->(r)
                MERGE (s)-[:HAS_THRESHOLD]->(t)
                """,
                cas=sub["cas_number"],
                name=f"{sub['name']} ({sub['abbreviation']})",
            )
            counts["substances"] += 1

    logger.info("regulatory_data_loaded", **counts)
    return counts
