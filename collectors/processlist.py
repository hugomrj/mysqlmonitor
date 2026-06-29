import logging

logger = logging.getLogger("mysql_monitor.collectors.processlist")


async def _get_pool():
    try:
        from mysql_pool import get_pool
        return await get_pool()
    except Exception as e:
        logger.error(f"No se pudo obtener pool: {e}")
        return None


async def collect() -> list:
    pool = await _get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SHOW FULL PROCESSLIST")
                rows = await cur.fetchall()

                return [
                    {
                        "id": row[0],
                        "user": row[1],
                        "host": row[2],
                        "db": row[3] or "",
                        "command": row[4],
                        "time": row[5],
                        "state": row[6] or "",
                        "info": row[7] if row[7] else None,
                    }
                    for row in rows
                ]

    except Exception as e:
        logger.error(f"Error en PROCESSLIST: {e}")
        return []