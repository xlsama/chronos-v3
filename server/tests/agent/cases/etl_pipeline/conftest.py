"""ETL pipeline test fixtures.

Provides:
- MySQL connection configs for all 3 databases
- Health check fixture that skips if databases are not available
"""

import aiomysql
import pytest
import pytest_asyncio

# Connection configs for the 3 ETL MySQL instances
SOURCE_DB_CONFIG = {
    "host": "localhost",
    "port": 13307,
    "user": "etl_user",
    "password": "sourcepass",
    "db": "source_db",
    "charset": "utf8mb4",
}

STAGING_DB_CONFIG = {
    "host": "localhost",
    "port": 13308,
    "user": "etl_user",
    "password": "stagingpass",
    "db": "staging_db",
    "charset": "utf8mb4",
}

TARGET_DB_CONFIG = {
    "host": "localhost",
    "port": 13309,
    "user": "etl_user",
    "password": "targetpass",
    "db": "target_db",
    "charset": "utf8mb4",
}


@pytest_asyncio.fixture(scope="module")
async def etl_databases():
    """Verify all 3 MySQL instances are accessible, skip if not."""
    configs = [
        ("source", SOURCE_DB_CONFIG),
        ("staging", STAGING_DB_CONFIG),
        ("target", TARGET_DB_CONFIG),
    ]
    for name, config in configs:
        try:
            pool = await aiomysql.create_pool(
                **config, minsize=1, maxsize=1, connect_timeout=5
            )
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
            pool.close()
            await pool.wait_closed()
        except Exception as e:
            pytest.skip(
                f"ETL MySQL '{name}' not available at "
                f"{config['host']}:{config['port']}: {e}"
            )

    yield {
        "source": SOURCE_DB_CONFIG,
        "staging": STAGING_DB_CONFIG,
        "target": TARGET_DB_CONFIG,
    }
