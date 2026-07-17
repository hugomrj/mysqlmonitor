import hashlib
import logging
import aiosqlite
import aiomysql
from pathlib import Path
from config_state import get_mysql_config_dict

logger = logging.getLogger("mysql_monitor.slow_cache")

DB_PATH = Path(__file__).parent.parent / "monitor.db"
MAX_CACHED = 10000


async def _get_mysql_conn():
    cfg = get_mysql_config_dict()
    return await aiomysql.connect(
        host=cfg.get("host", "localhost"),
        port=int(cfg.get("port", 3306)),
        user=cfg.get("user", "root"),
        password=cfg.get("passwd") or cfg.get("password", ""),
        connect_timeout=5,
        autocommit=True
    )


async def sync_slow_to_sqlite():
    """Lee mysql.slow_log y vuelca los nuevos registros a SQLite."""
    try:
        conn = await _get_mysql_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """SELECT start_time, user_host, query_time, lock_time, 
                              rows_sent, rows_examined, db, sql_text 
                       FROM mysql.slow_log 
                       ORDER BY start_time DESC LIMIT 500"""
                )
                rows = await cur.fetchall()
        finally:
            conn.close()

        if not rows: return 0

        new_count = 0
        async with aiosqlite.connect(DB_PATH) as db:
            for r in rows:
                try:
                    raw_sql = r["sql_text"]
                    if isinstance(raw_sql, bytes):
                        raw_sql = raw_sql.decode("utf-8", errors="replace")
                    
                    # Limpiar basura de MySQL
                    lines = raw_sql.strip().split('\n')
                    clean_sql = '\n'.join([l for l in lines if not l.lower().startswith(('use ', 'set timestamp', 'set names'))])

                    # PARSEO SEGURO DE FECHAS Y TIEMPOS
                    time_str = "—"
                    if r["start_time"]:
                        try:
                            time_str = r["start_time"].strftime("%Y-%m-%d %H:%M:%S.%f")
                        except:
                            time_str = str(r["start_time"])

                    qt = 0.0
                    if r["query_time"] is not None:
                        try:
                            qt = float(r["query_time"])
                        except TypeError:
                            try:
                                qt = float(r["query_time"].total_seconds())
                            except:
                                qt = 0.0

                    lt = 0.0
                    if r["lock_time"] is not None:
                        try:
                            lt = float(r["lock_time"])
                        except TypeError:
                            try:
                                lt = float(r["lock_time"].total_seconds())
                            except:
                                lt = 0.0

                    sql_hash = hashlib.md5((time_str + clean_sql).encode("utf-8")).hexdigest()

                    await db.execute(
                        """INSERT INTO slow_queries 
                           (start_time, user_host, query_time, lock_time, rows_sent, rows_examined, db, sql_text, sql_hash)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            time_str,
                            r["user_host"],
                            qt,
                            lt,
                            r["rows_sent"] or 0,
                            r["rows_examined"] or 0,
                            r["db"],
                            clean_sql,
                            sql_hash
                        )
                    )
                    new_count += 1
                except aiosqlite.IntegrityError:
                    pass # Duplicado, ya existe en SQLite. Lo ignoramos silenciosamente.
                except Exception as inner_e:
                    logger.error(f"Error insertando 1 slow query real: {inner_e}")

            await db.commit()

            # Limpiar excedente
            await db.execute(
                """DELETE FROM slow_queries WHERE id NOT IN (
                    SELECT id FROM slow_queries ORDER BY id DESC LIMIT ?
                )""", (MAX_CACHED,)
            )
            await db.commit()

        if new_count > 0:
            logger.info(f"Sincronizadas {new_count} consultas lentas nuevas a SQLite")
        return new_count

    except Exception as e:
        logger.error(f"Error sincronizando slow_log: {e}")
        raise Exception(f"Error crítico sincronizando slow_log: {e}")


async def get_cached_queries(
    min_time: float = None,
    max_time: float = None,
    db_name: str = None,
    user: str = None,
    date_from: str = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Lee consultas lentas desde SQLite (con sincronización previa)."""
    
    try:
        await sync_slow_to_sqlite()
    except Exception as sync_err:
        return {"total": 0, "data": [], "error": str(sync_err)}

    conditions = []
    params = []

    if min_time is not None:
        conditions.append("query_time >= ?")
        params.append(min_time)
    if max_time is not None:
        conditions.append("query_time <= ?")
        params.append(max_time)
    if db_name:
        conditions.append("db = ?")
        params.append(db_name)
    if user:
        conditions.append("user_host LIKE ?")
        params.append(f"%{user}%")
    if date_from:
        conditions.append("date(start_time) >= ?")
        params.append(date_from)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                f"SELECT COUNT(*) FROM slow_queries{where}", params
            )
            total = (await cursor.fetchone())[0]

            cursor = await db.execute(
                f"""SELECT id, start_time, user_host, query_time, lock_time,
                           rows_sent, rows_examined, db, sql_text
                    FROM slow_queries{where}
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?""",
                params + [limit, offset]
            )
            rows = await cursor.fetchall()

        return {
            "total": total,
            "data": [
                {
                    "id": r[0], "start_time": r[1], "user_host": r[2],
                    "query_time": r[3], "lock_time": r[4],
                    "rows_sent": r[5], "rows_examined": r[6],
                    "db": r[7], "sql_text": r[8],
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.error(f"Error leyendo SQLite slow: {e}")
        return {"total": 0, "data": [], "error": str(e)}


async def get_slow_databases() -> list:
    """Bases de datos distinct del caché local."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT db FROM slow_queries "
            "WHERE db IS NOT NULL AND db != '' ORDER BY db"
        )
        return [r[0] for r in await cursor.fetchall()]


async def get_slow_users() -> list:
    """Usuarios distinct del caché local."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT user_host FROM slow_queries "
            "WHERE user_host IS NOT NULL AND user_host != '' "
            "ORDER BY user_host"
        )
        raw_list = await cursor.fetchall()
    
    users = set()
    for (uh,) in raw_list:
        match = uh.strip().split('[')[0].split('@')[0].strip()
        if match:
            users.add(match)
    return sorted(users)


async def clear_cached_queries() -> int:
    """Borra todo el caché de consultas lentas de SQLite."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM slow_queries")
        total = (await cursor.fetchone())[0]
        await db.execute("DELETE FROM slow_queries")
        await db.commit()
    return total


async def cache_slow_queries(min_time: float = 0.5, limit: int = 100) -> int:
    """Mantengo esta función por si el router la llama, pero redirijo al sync nuevo."""
    return await sync_slow_to_sqlite()