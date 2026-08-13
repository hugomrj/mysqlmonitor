"""
Servicio de consultas recientes en memoria (performance_schema)
NO persiste en SQLite, solo mantiene un buffer circular en RAM.
"""
import asyncio
import logging
import time
from collections import deque
from datetime import datetime

from mysql_pool import get_pool

logger = logging.getLogger("recent_queries")

# Buffer circular en memoria (NO SQLite)
_recent_queries = deque(maxlen=500)
_lock = asyncio.Lock()

# Task para el loop de recolección
_task: asyncio.Task | None = None


async def start():
    """Inicia el loop de recolección de consultas recientes."""
    global _task
    if _task is not None:
        return
    _task = asyncio.create_task(_collect_loop())
    logger.info("Recent queries service iniciado")


async def stop():
    """Detiene el loop de recolección."""
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
        logger.info("Recent queries service detenido")


async def _collect_loop():
    """Loop que recolecta consultas cada 2 segundos."""
    while True:
        try:
            await collect_recent_queries()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error recolectando consultas recientes: {e}")
        await asyncio.sleep(2)



async def collect_recent_queries():
    """Lee las últimas consultas de performance_schema.
    CORREGIDO para MySQL 5.7: usa CURRENT_SCHEMA en lugar de SCHEMA_NAME."""
    pool = await get_pool()
    if not pool:
        return []
    
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # CORRECCIÓN: CURRENT_SCHEMA en lugar de SCHEMA_NAME
                await cur.execute("""
                    SELECT 
                        t.PROCESSLIST_HOST AS client_host,
                        t.PROCESSLIST_USER AS username,
                        e.SQL_TEXT,
                        e.CURRENT_SCHEMA AS database_name,
                        ROUND(e.TIMER_WAIT / 1000000000, 2) AS query_time_ms,
                        e.ROWS_EXAMINED,
                        e.ROWS_SENT,
                        e.DIGEST_TEXT
                    FROM performance_schema.events_statements_history_long e
                    JOIN performance_schema.threads t ON e.THREAD_ID = t.THREAD_ID
                    WHERE e.SQL_TEXT IS NOT NULL
                      AND e.SQL_TEXT NOT LIKE 'performance_schema%%'
                      AND e.SQL_TEXT NOT LIKE 'information_schema%%'
                      AND e.SQL_TEXT NOT LIKE 'SHOW %%'
                    ORDER BY e.TIMER_END DESC
                    LIMIT 100
                """)
                rows = await cur.fetchall()
        
        async with _lock:
            existing_sqls = {q["sql_text"] for q in _recent_queries}
            
            for row in rows:
                sql_text = row[2]
                if sql_text in existing_sqls:
                    continue
                    
                client_ip = row[0].split(":")[0] if row[0] else "unknown"
                
                _recent_queries.appendleft({
                    "timestamp": datetime.now().isoformat(),
                    "client_ip": client_ip,
                    "client_host": row[0],
                    "username": row[1],
                    "sql_text": sql_text,
                    "database": row[3],
                    "query_time_ms": float(row[4]) if row[4] else 0,
                    "rows_examined": row[5] or 0,
                    "rows_sent": row[6] or 0,
                })
                existing_sqls.add(sql_text)
        
        return list(_recent_queries)
        
    except Exception as e:
        logger.error(f"Error leyendo performance_schema: {e}")
        return []




async def get_recent_queries(limit: int = 100, min_time_ms: float = None, 
                              database: str = None, username: str = None):
    """Obtiene consultas recientes con filtros opcionales."""
    async with _lock:
        queries = list(_recent_queries)
    
    # Aplicar filtros
    if min_time_ms is not None:
        queries = [q for q in queries if q["query_time_ms"] >= min_time_ms]
    
    if database:
        queries = [q for q in queries if q["database"] == database]
    
    if username:
        queries = [q for q in queries if q["username"] == username]
    
    return queries[:limit]


async def get_stats():
    """Estadísticas de las consultas recientes."""
    async with _lock:
        queries = list(_recent_queries)
    
    if not queries:
        return {"total": 0, "avg_time_ms": 0, "max_time_ms": 0}
    
    times = [q["query_time_ms"] for q in queries]
    return {
        "total": len(queries),
        "avg_time_ms": round(sum(times) / len(times), 2),
        "max_time_ms": round(max(times), 2),
        "min_time_ms": round(min(times), 2),
    }


async def clear():
    """Limpia el buffer de consultas recientes."""
    async with _lock:
        _recent_queries.clear()
    logger.info("Buffer de consultas recientes limpiado")