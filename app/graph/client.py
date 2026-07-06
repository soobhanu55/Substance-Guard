from __future__ import annotations

from functools import lru_cache

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import get_settings


@lru_cache(maxsize=1)
def get_driver() -> AsyncDriver:
    settings = get_settings()
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


async def close_driver() -> None:
    driver = get_driver()
    await driver.close()
    get_driver.cache_clear()
