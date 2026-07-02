import hashlib
import logging
import aiosqlite
from pathlib import Path

logger = logging.getLogger("mysql_monitor.queries_cache")

DB_PATH = Path(__file__).parent.parent / "monitor.db"
MAX_CACHED = 5000  # Máximo de consultas a guardar


async def cache_queries(queries: list) -> int:
    """Guarda consultas del general_log en SQLite."""
    if not queries:
        return 0

    new_count = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for q in queries:
            if not q["sql_text"]:
                continue

            sql_hash = hashlib.md5(
                (q["event_time"] + q["sql_text"]).encode("utf-8")
            ).hexdigest()

            try:
                await db.execute(
                    """INSERT INTO queries_cache
                       (event_time, user_host, user_name, command_type,
                        db, sql_text, sql_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (q["event_time"], q["user_host"], q["user"],
                     q["command_type"], q["db"], q["sql_text"], sql_hash)
                )
                new_count += 1
            except aiosqlite.IntegrityError:
                pass

        await db.commit()

        # Limpiar excedente (mantener los más recientes)
        await db.execute(
            """DELETE FROM queries_cache WHERE id NOT IN (
                SELECT id FROM queries_cache
                ORDER BY event_time DESC LIMIT ?
            )""", (MAX_CACHED,)
        )
        await db.commit()

    if new_count > 0:
        logger.info(f"Cacheadas {new_count} consultas nuevas")
    return new_count


async def get_cached_queries(
    user: str = None,
    db_name: str = None,
    date_from: str = None,
    min_time: float = None,
    max_time: float = None,
    search: str = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Lee consultas cacheadas con filtros."""
    conditions = []
    params = []

    if user:
        conditions.append("user_name = ?")
        params.append(user)
    if db_name:
        conditions.append("db = ?")
        params.append(db_name)
    if date_from:
        conditions.append("date(event_time) >= ?")
        params.append(date_from)
    if search:
        conditions.append("sql_text LIKE ?")
        params.append(f"%{search}%")

    # min_time y max_time no aplican aquí (general_log no tiene duración)
    # pero los aceptamos por compatibilidad con el frontend

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM queries_cache{where}", params
        )
        total = (await cursor.fetchone())[0]

        cursor = await db.execute(
            f"""SELECT id, event_time, user_host, user_name, command_type,
                       db, sql_text
                FROM queries_cache{where}
                ORDER BY event_time DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset]
        )
        rows = await cursor.fetchall()

    return {
        "total": total,
        "data": [
            {
                "id": r[0], "event_time": r[1], "user_host": r[2],
                "user": r[3], "command_type": r[4],
                "db": r[5], "sql_text": r[6],
                "query_time": 0,  
                "lock_time": "—",
                "rows_examined": 0,
                "rows_sent": 0,
            }
            for r in rows
        ]
    }


async def get_query_users() -> list:
    """Usuarios distinct del caché."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT user_name FROM queries_cache "
            "WHERE user_name IS NOT NULL AND user_name != '' "
            "ORDER BY user_name"
        )
        return [r[0] for r in await cursor.fetchall()]


async def get_query_databases() -> list:
    """Bases de datos distinct del caché."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT db FROM queries_cache "
            "WHERE db IS NOT NULL AND db != '' ORDER BY db"
        )
        return [r[0] for r in await cursor.fetchall()]


async def clear_cached_queries() -> int:
    """Borra todo el caché de consultas."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM queries_cache")
        total = (await cursor.fetchone())[0]
        await db.execute("DELETE FROM queries_cache")
        await db.commit()
    return total