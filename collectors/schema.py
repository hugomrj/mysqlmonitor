import logging

logger = logging.getLogger("mysql_monitor.collectors.schema")


async def _get_pool():
    try:
        from mysql_pool import get_pool
        return await get_pool()
    except Exception as e:
        logger.error(f"No se pudo obtener pool: {e}")
        return None


def _bytes_to_human(b: int) -> str:
    if b == 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


async def collect_databases() -> list:
    pool = await _get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT
                        s.SCHEMA_NAME,
                        ANY_VALUE(s.DEFAULT_CHARACTER_SET_NAME),
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

                rows = await cur.fetchall()
                result = []
                for row in rows:
                    size_bytes = row[2] or 0
                    result.append({
                        "name": row[0],
                        "collation": row[1],
                        "size_bytes": size_bytes,
                        "size_human": _bytes_to_human(size_bytes),
                        "tables": row[3] or 0,
                        "last_modified": str(row[4]) if row[4] else None,
                    })
                return result

    except Exception as e:
        logger.error(f"Error leyendo esquemas: {e}")
        return []


async def collect_tables(schema: str) -> list:
    pool = await _get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT
                        TABLE_NAME,
                        ENGINE,
                        DATA_LENGTH,
                        INDEX_LENGTH,
                        (DATA_LENGTH + INDEX_LENGTH),
                        TABLE_ROWS,
                        AUTO_INCREMENT,
                        CREATE_TIME,
                        UPDATE_TIME
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = %s
                        AND TABLE_TYPE = 'BASE TABLE'
                    ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC
                """, (schema,))

                rows = await cur.fetchall()
                result = []
                for row in rows:
                    data_len = row[2] or 0
                    idx_len = row[3] or 0
                    total = row[4] or 0
                    result.append({
                        "name": row[0],
                        "engine": row[1] or "",
                        "data_length": data_len,
                        "data_human": _bytes_to_human(data_len),
                        "index_length": idx_len,
                        "index_human": _bytes_to_human(idx_len),
                        "total_length": total,
                        "total_human": _bytes_to_human(total),
                        "rows": row[5] or 0,
                        "auto_increment": row[6],
                        "create_time": str(row[7]) if row[7] else None,
                        "update_time": str(row[8]) if row[8] else None,
                    })
                return result

    except Exception as e:
        logger.error(f"Error leyendo tablas de {schema}: {e}")
        return []


async def collect_top_tables(limit: int = 8) -> list:
    pool = await _get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT
                        TABLE_SCHEMA,
                        TABLE_NAME,
                        (DATA_LENGTH + INDEX_LENGTH)
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA NOT IN
                        ('mysql','information_schema','performance_schema','sys')
                        AND TABLE_TYPE = 'BASE TABLE'
                    ORDER BY 3 DESC
                    LIMIT %s
                """, (limit,))

                rows = await cur.fetchall()
                return [
                    {
                        "schema": row[0],
                        "table": row[1],
                        "size_bytes": row[2] or 0,
                        "size_human": _bytes_to_human(row[2] or 0),
                    }
                    for row in rows
                ]

    except Exception as e:
        logger.error(f"Error en top tables: {e}")
        return []