import hashlib
import logging
import aiosqlite
import aiomysql
from pathlib import Path
from config_state import get_mysql_config_dict

logger = logging.getLogger("mysql_monitor.queries_cache")

DB_PATH = Path(__file__).parent.parent / "monitor.db"
MAX_CACHED = 5000 

def _ps_to_secs(ps):
    if ps is None: return 0.0
    return round(ps / 1_000_000_000_000, 6)

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

def parse_op(sql):
    if not sql: return 'OTHER'
    first = sql.strip().upper().split()[0]
    return ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'REPLACE', 'CALL', 'SET'].__contains__(first) and first or 'OTHER'

async def sync_performance_to_sqlite():
    """Lee el performance_schema y lo vuelca/actualiza en SQLite."""
    try:
        conn = await _get_mysql_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT DIGEST, DIGEST_TEXT, SCHEMA_NAME, COUNT_STAR, SUM_TIMER_WAIT, AVG_TIMER_WAIT, SUM_ROWS_EXAMINED, SUM_ROWS_SENT FROM performance_schema.events_statements_summary_by_digest WHERE DIGEST_TEXT IS NOT NULL"
                )
                rows = await cur.fetchall()
        finally:
            conn.close()

        if not rows: return 0

        new_count = 0
        async with aiosqlite.connect(DB_PATH) as db:
            for r in rows:
                raw_sql = r["DIGEST_TEXT"]
                sql_hash = r["DIGEST"] 
                
                avg_time = _ps_to_secs(r["AVG_TIMER_WAIT"])

                try:
                    await db.execute(
                        """INSERT INTO queries_cache 
                           (sql_hash, event_time, user_host, user_name, command_type, db, sql_text, query_time, rows_examined, rows_sent, exec_count)
                           VALUES (?, datetime('now'), 'system', 'system', ?, ?, ?, ?, ?, ?, ?)""",
                        (sql_hash, parse_op(raw_sql), r["SCHEMA_NAME"], raw_sql, avg_time, r["SUM_ROWS_EXAMINED"] or 0, r["SUM_ROWS_SENT"] or 0, r["COUNT_STAR"])
                    )
                    new_count += 1
                except aiosqlite.IntegrityError:
                    await db.execute(
                        """UPDATE queries_cache SET 
                           event_time = datetime('now'),
                           exec_count = ?,
                           query_time = ?,
                           rows_examined = ?,
                           rows_sent = ?
                           WHERE sql_hash = ?""",
                        (r["COUNT_STAR"], avg_time, r["SUM_ROWS_EXAMINED"] or 0, r["SUM_ROWS_SENT"] or 0, sql_hash)
                    )

            await db.commit()

            await db.execute(
                """DELETE FROM queries_cache WHERE id NOT IN (
                    SELECT id FROM queries_cache ORDER BY id DESC LIMIT ?
                )""", (MAX_CACHED,)
            )
            await db.commit()

        if new_count > 0:
            logger.info(f"Sincronizadas {new_count} consultas nuevas a SQLite")
        return new_count

    except Exception as e:
        logger.error(f"Error sincronizando performance_schema: {e}")
        return 0


async def get_cached_queries(
    user: str = None,
    db_name: str = None,
    date_from: str = None, 
    min_time: float = None, 
    max_time: float = None, 
    search: str = None,
    sql_type: str = "SELECT",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Lee consultas cacheadas con filtros."""
    
    # SINCRONIZA AL INSTANTE ANTES DE LEER
    await sync_performance_to_sqlite()

    conditions = []
    params = []

    if sql_type == "SELECT":
        conditions.append("command_type = ?")
        params.append("SELECT")
    elif sql_type == "OTHER":
        conditions.append("command_type != ?")
        params.append("SELECT")

    if user:
        conditions.append("user_name = ?")
        params.append(user)
    if db_name:
        conditions.append("db = ?")
        params.append(db_name)
    if date_from:
        conditions.append("date(event_time) >= ?")
        params.append(date_from)
    if min_time is not None:
        conditions.append("query_time >= ?")
        params.append(min_time)
    if search:
        conditions.append("sql_text LIKE ?")
        params.append(f"%{search}%")

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM queries_cache{where}", params
        )
        total = (await cursor.fetchone())[0]

        cursor = await db.execute(
            f"""SELECT id, event_time, user_host, user_name, command_type,
                       db, sql_text, query_time, lock_time, rows_examined, rows_sent, exec_count
                FROM queries_cache{where}
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
                "user": r[3], "command_type": r[4],
                "db": r[5], "sql_text": r[6],
                "query_time": r[7] or 0,  
                "lock_time": r[8] or "—",
                "rows_examined": r[9] or 0,
                "rows_sent": r[10] or 0,
                "exec_count": r[11] or 1
            }
            for r in rows
        ]
    }


async def get_query_users() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT user_name FROM queries_cache "
            "WHERE user_name IS NOT NULL AND user_name != '' "
            "ORDER BY user_name"
        )
        return [r[0] for r in await cursor.fetchall()]


async def get_query_databases() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT db FROM queries_cache "
            "WHERE db IS NOT NULL AND db != '' ORDER BY db"
        )
        return [r[0] for r in await cursor.fetchall()]


async def clear_cached_queries() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM queries_cache")
        total = (await cursor.fetchone())[0]
        await db.execute("DELETE FROM queries_cache")
        await db.commit()
    return total