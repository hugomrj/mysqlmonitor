# collectors/general_log.py
import logging

logger = logging.getLogger("mysql_monitor.collectors.general_log")

_pool = None

async def _get_pool():
    global _pool
    if _pool is None:
        try:
            from mysql_pool import get_pool
            _pool = await get_pool()
        except Exception as e:
            logger.error(f"No se pudo importar pool: {e}")
            _pool = False
    return _pool if _pool else None


async def collect(limit: int = 200) -> list:
    """Lee el General Query Log de MySQL.
    IMPORTANTE: Después de leer, se debe TRUNCAR la tabla
    para que no crezca infinitamente."""
    pool = await _get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Verificar que general_log exista como tabla
                await cur.execute("""
                    SELECT COUNT(*) FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = 'mysql' AND TABLE_NAME = 'general_log'
                """)
                exists = (await cur.fetchone())[0]

                if not exists:
                    logger.warning(
                        "mysql.general_log no existe como tabla. "
                        "Ejecuta: SET GLOBAL log_output = 'TABLE';"
                    )
                    return []

                await cur.execute("""
                    SELECT
                        event_time,
                        user_host,
                        command_type,
                        argument
                    FROM mysql.general_log
                    WHERE command_type IN ('Query', 'Execute')
                    ORDER BY event_time DESC
                    LIMIT %s
                """, (limit,))

                rows = await cur.fetchall()
                result = []
                for row in rows:
                    argument = row[3]
                    if isinstance(argument, bytes):
                        argument = argument.decode("utf-8", errors="replace")

                    # Ignorar consultas internas del monitor
                    sql = (argument or "").strip()
                    if sql.upper().startswith("SHOW ") and "SLOW_LOG" in sql.upper():
                        continue
                    if sql.upper().startswith("SHOW ") and "GENERAL_LOG" in sql.upper():
                        continue
                    if "TRUNCATE" in sql.upper() and "GENERAL_LOG" in sql.upper():
                        continue

                    # Extraer usuario del user_host
                    user = ""
                    if row[1]:
                        user = row[1].split("[")[0].split("@")[0].strip()

                    # Intentar determinar la base de datos
                    db = ""
                    sql_upper = sql.upper()
                    for prefix in ["USE ", "FROM ", "INTO ", "UPDATE ", "TABLE "]:
                        idx = sql_upper.find(prefix)
                        if idx >= 0:
                            candidate = sql[idx + len(prefix):].strip().strip("`").split(".")[0].split("`")[0].split(" ")[0].split(";")[0]
                            if candidate and not candidate.upper().startswith(("SELECT", "WHERE", "SET", "INSERT", "UPDATE", "DELETE", "VALUES")):
                                db = candidate
                                break

                    result.append({
                        "event_time": str(row[0]),
                        "user_host": row[1] or "",
                        "user": user,
                        "command_type": row[2] or "Query",
                        "db": db,
                        "sql_text": sql,
                    })

                return result

    except Exception as e:
        logger.error(f"Error leyendo general_log: {e}")
        return []


async def truncate_log() -> bool:
    """Trunca la tabla general_log para liberar espacio."""
    pool = await _get_pool()
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("TRUNCATE TABLE mysql.general_log")
                await conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error truncando general_log: {e}")
        return False