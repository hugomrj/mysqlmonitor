import logging

logger = logging.getLogger("mysql_monitor.collectors.slow")

# Importar tarde para no romper toda la app si aiomysql falla
_pool = None

async def _get_pool():
    global _pool
    if _pool is None:
        try:
            from mysql_pool import get_pool
            _pool = await get_pool()
        except Exception as e:
            logger.error(f"No se pudo importar pool: {e}")
            _pool = False  # False = ya intentó y falló, no reintentar
    return _pool if _pool else None


async def collect(min_time: float = 2.0, limit: int = 50) -> list:
    """Lee el Slow Query Log de MySQL 5.7.
    Requiere: slow_query_log=ON y log_output='TABLE'"""
    pool = await _get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Verificar que slow_log exista como tabla
                await cur.execute("""
                    SELECT COUNT(*) FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = 'mysql' AND TABLE_NAME = 'slow_log'
                """)
                exists = (await cur.fetchone())[0]

                if not exists:
                    logger.warning(
                        "mysql.slow_log no existe como tabla. "
                        "Ejecuta: SET GLOBAL log_output = 'TABLE';"
                    )
                    return []

                await cur.execute("""
                    SELECT
                        start_time,
                        user_host,
                        query_time,
                        lock_time,
                        rows_sent,
                        rows_examined,
                        db,
                        sql_text
                    FROM mysql.slow_log
                    WHERE query_time > %s
                    ORDER BY start_time DESC
                    LIMIT %s
                """, (min_time, limit))

                rows = await cur.fetchall()
                result = []
                for row in rows:
                    qt = row[2]
                    if hasattr(qt, "total_seconds"):
                        qt_seconds = qt.total_seconds()
                    else:
                        qt_seconds = float(qt)

                    result.append({
                        "start_time": str(row[0]),
                        "user_host": row[1],
                        "query_time": round(qt_seconds, 2),
                        "lock_time": str(row[3]),
                        "rows_sent": row[4] or 0,
                        "rows_examined": row[5] or 0,
                        "db": row[6] or "",
                        "sql_text": row[7] or "",
                    })

                return result

    except Exception as e:
        logger.error(f"Error leyendo slow_log: {e}")
        return []