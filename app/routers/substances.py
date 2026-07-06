from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.graph.queries import get_substance_regulations

router = APIRouter()


@router.get("/substance/{cas_number}/regulations")
async def substance_regulations(cas_number: str):
    result = await get_substance_regulations(cas_number)
    if result is None:
        raise HTTPException(status_code=404, detail=f"CAS {cas_number} not found in the regulatory graph.")
    return result
