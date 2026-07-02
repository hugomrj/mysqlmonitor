import hashlib
import logging
import aiosqlite
from pathlib import Path
from collectors.slow_queries import collect

logger = logging.getLogger("mysql_monitor.slow_cache")

DB_PATH = Path(__file__).parent.parent / "monitor.db"


async def cache_slow_queries(min_time: float = 0.5, limit: int = 100) -> int:
    """Lee slow_log de MySQL y guarda solo las nuevas en SQLite."""
    queries = await collect(min_time=min_time, limit=limit)
    if not queries:
        return 0

    new_count = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for q in queries:

            raw_sql = q["sql_text"]
            if isinstance(raw_sql, bytes):
                raw_sql = raw_sql.decode("utf-8", errors="replace")
            sql_hash = hashlib.md5(
                (q["start_time"] + raw_sql).encode("utf-8")
            ).hexdigest()


            # Ya existe? (IGNORE por el UNIQUE INDEX)
            try:
                await db.execute(
                    """INSERT INTO slow_queries
                       (start_time, user_host, query_time, lock_time,
                        rows_sent, rows_examined, db, sql_text, sql_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (q["start_time"], q["user_host"], q["query_time"],
                     q["lock_time"], q["rows_sent"], q["rows_examined"],
                     q["db"], raw_sql, sql_hash)
                )
                new_count += 1
            except aiosqlite.IntegrityError:
                pass  # Duplicado, ignorar

        await db.commit()

    if new_count > 0:
        logger.info(f"Cacheadas {new_count} consultas lentas nuevas")
    return new_count


async def get_cached_queries(
    min_time: float = None,
    max_time: float = None,
    db_name: str = None,
    user: str = None,
    date_from: str = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Lee consultas cacheadas con filtros."""
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

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM slow_queries{where}", params
        )
        total = (await cursor.fetchone())[0]

        cursor = await db.execute(
            f"""SELECT id, start_time, user_host, query_time, lock_time,
                       rows_sent, rows_examined, db, sql_text
                FROM slow_queries{where}
                ORDER BY start_time DESC
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




async def get_slow_databases() -> list:
    """Bases de datos distinct del caché."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT db FROM slow_queries "
            "WHERE db IS NOT NULL AND db != '' ORDER BY db"
        )
        return [r[0] for r in await cursor.fetchall()]


async def clear_cached_queries() -> int:
    """Borra todo el caché de consultas lentas."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM slow_queries")
        total = (await cursor.fetchone())[0]
        await db.execute("DELETE FROM slow_queries")
        await db.commit()
    return total



async def get_slow_users() -> list:
    """Usuarios distinct del caché (parseados desde user_host)."""
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