# services/recent_queries.py
"""
Servicio de consultas recientes en memoria (performance_schema)
NO persiste en SQLite, solo mantiene un buffer circular en RAM.
Filtrado: Solo SELECTs reales, sin ruido interno.
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
_permission_error = None




async def get_permission_error():
    """Devuelve el error de permisos actual (si existe)."""
    return _permission_error






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
    """Lee las últimas consultas de performance_schema."""
    global _permission_error
    
    pool = await get_pool()
    if not pool:
        return []
    
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
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
                      AND e.SQL_TEXT LIKE '%SELECT%'
                      AND e.SQL_TEXT NOT LIKE '%performance_schema%'
                      AND e.SQL_TEXT NOT LIKE '%information_schema%'
                      AND e.SQL_TEXT NOT LIKE 'SELECT 1'
                      AND e.SQL_TEXT NOT LIKE 'SELECT 1 %'
                      AND e.SQL_TEXT NOT LIKE '%FROM mysql.slow_log%'
                      AND e.SQL_TEXT NOT LIKE 'SELECT @@%'
                      AND e.SQL_TEXT NOT LIKE 'SET %'
                      AND e.SQL_TEXT NOT LIKE 'SHOW %'
                      AND e.SQL_TEXT NOT LIKE 'USE %'
                    ORDER BY e.TIMER_END DESC
                    LIMIT 100
                """)
                rows = await cur.fetchall()
        
        # Si llegó aquí, no hay error
        _permission_error = None
        
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
        error_str = str(e)
        
        if 'command denied' in error_str.lower() or '1142' in error_str:
            _permission_error = (
                "⚠️ Sin permisos para leer consultas. "
                "El usuario de MySQL no tiene acceso a performance_schema. "
                "Contacte al DBA para otorgar permisos de lectura sobre performance_schema."
            )
            logger.error(f"⛔ PERMISOS INSUFICIENTES (recent): {error_str}")
        else:
            _permission_error = f"⚠️ Error al leer consultas: {error_str[:200]}"
            logger.error(f"Error leyendo performance_schema: {e}")
        
        return []



    


async def get_recent_queries(limit: int = 100, min_time_ms: float = None, 
                              database: str = None, username: str = None):
    """Obtiene consultas recientes con filtros opcionales."""
    async with _lock:
        queries = list(_recent_queries)
    
    if min_time_ms is not None:
        queries = [q for q in queries if q["query_time_ms"] >= min_time_ms]
    
    if database:
        queries = [q for q in queries if q["database"] == database]
    
    if username:
        queries = [q for q in queries if q["username"] == username]
    
    return queries[:limit]


async def get_stats():
    """Estadísticas de las consultas recientes, incluyendo % de lentas."""
    # Importar aquí para obtener el umbral actual
    from database import load_config
    
    async with _lock:
        queries = list(_recent_queries)
    
    if not queries:
        return {
            "total": 0,
            "avg_time_ms": 0,
            "max_time_ms": 0,
            "min_time_ms": 0,
            "slow_count": 0,
            "slow_percentage": 0,
        }
    
    times = [q["query_time_ms"] for q in queries]
    total = len(queries)
    
    # Obtener el umbral configurado (en segundos) y convertir a ms
    try:
        cfg = await load_config()
        threshold_ms = float(cfg.slow_query_threshold) * 1000
    except Exception:
        threshold_ms = 3000  # Default 3 segundos
    
    # Contar consultas lentas (superan el umbral)
    slow_count = sum(1 for t in times if t >= threshold_ms)
    slow_percentage = round((slow_count / total) * 100, 1) if total > 0 else 0
    
    return {
        "total": total,
        "avg_time_ms": round(sum(times) / total, 2),
        "max_time_ms": round(max(times), 2),
        "min_time_ms": round(min(times), 2),
        "slow_count": slow_count,
        "slow_percentage": slow_percentage,
        "threshold_ms": threshold_ms,
    }

