from fastapi import APIRouter, Query
from collectors.schema import collect_databases, collect_tables, collect_top_tables

router = APIRouter(prefix="/api/databases", tags=["databases"])


@router.get("")
async def get_databases():
    return await collect_databases()


@router.get("/top-tables")
async def get_top_tables(limit: int = Query(default=8, ge=1, le=50)):
    return await collect_top_tables(limit)


@router.get("/{schema}/tables")
async def get_tables(schema: str):
    return await collect_tables(schema)


# TEMPORAL — Para diagnosticar el problema
@router.get("/debug")
async def debug_databases():
    """Ejecuta la consulta SQL raw y devuelve lo que MySQL devuelve."""
    try:
        from mysql_pool import get_pool
        pool = await get_pool()
        if pool is None:
            return {"error": "No hay pool de conexiones"}

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Consulta 1: simple, sin JOIN
                await cur.execute("""
                    SELECT SCHEMA_NAME
                    FROM information_schema.SCHEMATA
                    WHERE SCHEMA_NAME NOT IN
                        ('mysql','information_schema','performance_schema','sys')
                """)
                simple = await cur.fetchall()

                # Consulta 2: con JOIN (la que usa el collector)
                await cur.execute("""
                    SELECT
                        s.SCHEMA_NAME,
                        s.DEFAULT_CHARACTER_SET_NAME,
                        COALESCE(SUM(t.DATA_LENGTH + t.INDEX_LENGTH), 0),
                        COUNT(t.TABLE_NAME),
                        MAX(t.UPDATE_TIME)
                    FROM information_schema.SCHEMATA s
                    LEFT JOIN information_schema.TABLES t
                        ON s.SCHEMA_NAME = t.TABLE_SCHEMA
                        AND t.TABLE_TYPE = 'BASE TABLE'
                    WHERE s.SCHEMA_NAME NOT IN
                        ('mysql','information_schema','performance_schema','sys')
                    GROUP BY s.SCHEMA_NAME
                    ORDER BY 3 DESC
                """)
                joined = await cur.fetchall()

                return {
                    "simple_query_rows": len(simple),
                    "simple_query_data": [r[0] for r in simple],
                    "joined_query_rows": len(joined),
                    "joined_query_raw": [str(r) for r in joined],
                }

    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}