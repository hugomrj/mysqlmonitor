# services/slow_cache.py
"""
Servicio de caché de consultas lentas.

Responsabilidades:
- Sincronizar performance_schema → SQLite cada 10 segundos (vía bucle en main.py)
- Proveer consultas a la web (solo lectura de SQLite)
- Filtrar consultas internas del monitor
- Manejar errores de permisos de forma clara
"""
import re
import hashlib
import logging
import aiosqlite
import aiomysql
from pathlib import Path
from typing import Optional, List, Dict, Any

from config_state import get_mysql_config_dict
from database import load_config

logger = logging.getLogger("mysql_monitor.slow_cache")

DB_PATH = Path(__file__).parent.parent / "monitor.db"
MAX_CACHED = 10000


# ══════════════════════════════════════════════════════════════
# ESTADO GLOBAL DEL SERVICIO
# ══════════════════════════════════════════════════════════════

_last_timer_end: int = 0
_permission_error: Optional[str] = None


async def get_permission_error() -> Optional[str]:
    """Devuelve el error de permisos actual (si existe)."""
    return _permission_error


def _reset_permission_error() -> None:
    """Limpia el error de permisos cuando las consultas vuelven a funcionar."""
    global _permission_error
    if _permission_error is not None:
        logger.info("✅ Conexión restaurada, limpiando error de permisos")
        _permission_error = None


def _set_permission_error(message: str) -> None:
    """Guarda un error de permisos para mostrarlo en la UI."""
    global _permission_error
    _permission_error = message


# ══════════════════════════════════════════════════════════════
# CONEXIÓN A MYSQL
# ══════════════════════════════════════════════════════════════

async def _get_mysql_pool():
    """
    Obtiene el pool compartido de MySQL.
    
    Si el pool está cerrado o no existe (por cambio de config en caliente),
    lo recrea usando la configuración actual.
    """
    from mysql_pool import get_pool, create_pool
    from database import load_config
    
    pool = await get_pool()
    
    # Si no hay pool, crearlo con la config actual
    if pool is None:
        logger.info("🔄 Pool no disponible, recreando con config actual...")
        cfg = await load_config()
        pool = await create_pool(cfg.mysql)
    
    return pool



# ══════════════════════════════════════════════════════════════
# PATRONES DE CONSULTAS INTERNAS (a ignorar)
# ══════════════════════════════════════════════════════════════

# Patrones que SIEMPRE indican consulta interna del sistema
INTERNAL_PATTERNS_STRICT = [
    r'performance_schema',
    r'information_schema',
    r'mysql\.slow_log',
    r'FROM\s+mysql\.',
    r'^\s*SHOW\s+',
    r'^\s*DESCRIBE\s+',
    r'^\s*DESC\s+',
    r'^\s*EXPLAIN\s+',
    r'^\s*SET\s+',
    r'^\s*USE\s+',
    r'^\s*SELECT\s+@@',
    r'SELECT\s+VERSION\s*\(',
    r'SELECT\s+DATABASE\s*\(',
    r'SELECT\s+CURRENT_USER',
    r'SCHEMA_NAME',
    r'ANY_VALUE\s*\(',
    r'DATA_LENGTH',
    r'INDEX_LENGTH',
    r'TABLE_ROWS',
    r'SHOW\s+TABLE\s+STATUS',
    r'SHOW\s+FULL\s+TABLES',
    r'SHOW\s+COLUMNS',
    r'SHOW\s+CREATE\s+TABLE',
    r'WHERE\s+1\s*=\s*0',
    r'/\*\s*ApplicationName',
]

# Solo "SELECT 1" exacto es health check (no "SELECT 5" ni "SELECT SLEEP")
HEALTH_CHECK_PATTERN = r'^\s*SELECT\s+1\s*$'



def _is_internal_query(sql_text: str) -> bool:
    """
    Detecta si una consulta es interna del monitor o ruido.
    
    ✅ NO filtra:
    - SELECT SLEEP() → consultas de prueba legítimas
    - SELECT BENCHMARK() → consultas de prueba legítimas
    - SELECT 5, SELECT 100, etc. → valores numéricos normales
    
    ❌ SÍ filtra:
    - SELECT 1 exacto (health checks)
    - Consultas a performance_schema/information_schema
    - SHOW, SET, USE, etc.
    """
    if not sql_text:
        return True
    
    sql_clean = sql_text.strip()
    sql_lower = sql_clean.lower()
    
    # Consultas muy cortas probablemente son ruido (excepto SELECT 1)
    if len(sql_clean) < 10:
        # Solo considerar interna si es exactamente "SELECT 1"
        if re.match(HEALTH_CHECK_PATTERN, sql_clean, re.IGNORECASE):
            return True
        # Otras consultas cortas: dejarlas pasar (ej: "SELECT 5")
        return False
    
    # Verificar patrones estrictos
    for pattern in INTERNAL_PATTERNS_STRICT:
        if re.search(pattern, sql_lower, re.IGNORECASE):
            return True
    
    return False








def _clean_sql(sql_text: str) -> str:
    """Limpia el SQL eliminando líneas de setup automático de MySQL."""
    if not sql_text:
        return ""
    
    lines = sql_text.strip().split('\n')
    prefixes_to_skip = ('use ', 'set timestamp', 'set names')
    
    cleaned = '\n'.join(
        line for line in lines
        if not line.lower().startswith(prefixes_to_skip)
    )
    return cleaned.strip()



def _extract_client_ip(host_raw: str) -> str:
    """
    Extrae la IP de PROCESSLIST_HOST.
    Formato típico: '192.168.1.5:54132' o 'localhost' o '192.168.1.5'
    """
    if not host_raw:
        return "unknown"
    
    # Quitar puerto si existe
    if ':' in host_raw:
        ip = host_raw.split(':')[0]
    else:
        ip = host_raw
    
    # Validar formato IP
    if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ip):
        return ip
    
    # Si es hostname o valor raro, devolverlo limpio
    return ip or "unknown"


def _build_sql_hash(timestamp: str, sql_text: str) -> str:
    """Genera un hash único para deduplicar consultas."""
    content = f"{timestamp}|{sql_text}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════
# SINCRONIZACIÓN: performance_schema → SQLite
# ══════════════════════════════════════════════════════════════

async def sync_slow_to_sqlite() -> int:
    """
    Sincroniza consultas lentas desde performance_schema a SQLite.
    
    Retorna: número de nuevas consultas insertadas.
    
    Este método es llamado únicamente por el bucle de main.py.
    La web NUNCA lo llama directamente (solo lee de SQLite).
    """
    global _last_timer_end
    
    threshold = await _get_threshold()
    rows = await _fetch_new_slow_queries(threshold)
    
    # ═══ CASO 1: Error de conexión/permisos ═══
    # _fetch_new_slow_queries retornó None → el error ya está registrado
    if rows is None:
        return 0
    
    # ═══ CASO 2: Conexión exitosa ═══
    # Si llegamos aquí, la conexión a MySQL FUNCIONA → limpiar cualquier error viejo
    # Esto es CLAVE: limpia el error incluso si rows tiene consultas ignoradas
    _reset_permission_error()
    
    # ═══ CASO 3: Sin consultas nuevas ═══
    if not rows:
        return 0
    
    # ═══ CASO 4: Hay consultas nuevas, procesarlas ═══
    new_count, skipped = await _persist_to_sqlite(rows, threshold)
    
    if new_count > 0 or skipped > 0:
        logger.info(
            f"📊 Sincronizadas {new_count} consultas >= {threshold}s "
            f"(ignoradas {skipped} internas)"
        )
    
    return new_count


async def _get_threshold() -> float:
    """Obtiene el umbral configurado para consultas lentas."""
    try:
        cfg = await load_config()
        return max(1.0, float(cfg.slow_query_threshold))
    except Exception as e:
        logger.warning(f"No se pudo cargar config, usando umbral 3.0: {e}")
        return 3.0


async def _fetch_new_slow_queries(threshold: float) -> Optional[List[Dict[str, Any]]]:
    """
    Consulta performance_schema para obtener consultas lentas nuevas.
    Usa el pool compartido que se actualiza en caliente.
    
    Retorna:
    - None: si hay error (ya registrado en _handle_sync_error)
    - Lista vacía: si no hay consultas nuevas
    - Lista con elementos: consultas nuevas para procesar
    """
    global _last_timer_end
    
    try:
        pool = await _get_mysql_pool()
        
        if pool is None:
            _set_permission_error(
                "No hay conexión a MySQL configurada. "
                "Configure la conexión en la sección de configuración."
            )
            logger.warning("⚠️ Sin pool MySQL disponible")
            return None
        
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT 
                        e.TIMER_END,
                        t.PROCESSLIST_HOST AS user_host,
                        t.PROCESSLIST_USER AS username,
                        e.SQL_TEXT AS sql_text,
                        e.CURRENT_SCHEMA AS db,
                        ROUND(e.TIMER_WAIT / 1000000000000, 6) AS query_time,
                        e.ROWS_EXAMINED AS rows_examined,
                        e.ROWS_SENT AS rows_sent,
                        FROM_UNIXTIME(e.TIMER_END / 1000000000000) AS start_time
                    FROM performance_schema.events_statements_history_long e
                    JOIN performance_schema.threads t ON e.THREAD_ID = t.THREAD_ID
                    WHERE e.SQL_TEXT IS NOT NULL
                      AND e.TIMER_END > %s
                      AND ROUND(e.TIMER_WAIT / 1000000000000, 6) >= %s
                      AND e.SQL_TEXT LIKE '%%SELECT%%'
                      AND e.SQL_TEXT NOT LIKE '%%performance_schema%%'
                      AND e.SQL_TEXT NOT LIKE '%%information_schema%%'
                      AND e.SQL_TEXT NOT LIKE 'SELECT 1'
                      AND e.SQL_TEXT NOT LIKE 'SELECT 1 %%'
                      AND e.SQL_TEXT NOT LIKE '%%FROM mysql.slow_log%%'
                      AND e.SQL_TEXT NOT LIKE 'SELECT @@%%'
                      AND e.SQL_TEXT NOT LIKE 'SET %%'
                      AND e.SQL_TEXT NOT LIKE 'SHOW %%'
                      AND e.SQL_TEXT NOT LIKE 'USE %%'
                    ORDER BY e.TIMER_END ASC
                    LIMIT 100
                    """,
                    (_last_timer_end, threshold)
                )
                return await cur.fetchall()
    
    except Exception as e:
        _handle_sync_error(e)
        return None


def _handle_sync_error(error: Exception) -> None:
    """Clasifica y registra errores de sincronización."""
    error_str = str(error).lower()
    
    if 'command denied' in error_str or '1142' in error_str:
        _set_permission_error(
            "Sin permisos para leer consultas. "
            "El usuario de MySQL no tiene acceso a performance_schema. "
            "Contacte al DBA para otorgar permisos de lectura sobre performance_schema."
        )
        logger.error(f"⛔ PERMISOS INSUFICIENTES: {error}")
    elif 'access denied' in error_str or '1045' in error_str:
        _set_permission_error(
            "Credenciales de MySQL incorrectas. "
            "Verifique el usuario y contraseña en la sección de configuración."
        )
        logger.error(f"⛔ CREDENCIALES INCORRECTAS: {error}")
    else:
        _set_permission_error(f"Error al sincronizar consultas: {str(error)[:200]}")
        logger.error(f"Error sincronizando slow_log: {error}")


async def _persist_to_sqlite(rows: List[Dict[str, Any]], threshold: float) -> tuple[int, int]:
    """
    Inserta las consultas en SQLite.
    
    Retorna: (cantidad_insertadas, cantidad_ignoradas)
    """
    global _last_timer_end
    
    new_count = 0
    skipped_internal = 0
    max_timer_end = _last_timer_end
    
    async with aiosqlite.connect(DB_PATH) as db:
        for row in rows:
            try:
                result = await _process_row(db, row, threshold)
                
                if result is None:
                    continue
                
                if result["inserted"]:
                    new_count += 1
                    if result["timer_end"] > max_timer_end:
                        max_timer_end = result["timer_end"]
                else:
                    skipped_internal += 1
                    
            except aiosqlite.IntegrityError:
                # Hash duplicado: ya existe, solo avanzar el marcador
                if row["TIMER_END"] > max_timer_end:
                    max_timer_end = row["TIMER_END"]
            except Exception as e:
                logger.error(f"Error procesando fila: {e}")
        
        await db.commit()
        await _cleanup_old_rows(db)
    
    _last_timer_end = max_timer_end
    return new_count, skipped_internal


async def _process_row(db, row: Dict[str, Any], threshold: float) -> Optional[Dict[str, Any]]:
    """
    Procesa una fila individual: valida, limpia e inserta en SQLite.
    
    Retorna dict con resultado o None si se debe saltar (no alcanza umbral).
    """
    timer_end = row["TIMER_END"]
    query_time = float(row["query_time"]) if row["query_time"] else 0.0
    
    # Doble validación de umbral (por seguridad)
    if query_time < threshold:
        return None
    
    # Limpiar SQL
    raw_sql = row["sql_text"]
    if isinstance(raw_sql, bytes):
        raw_sql = raw_sql.decode("utf-8", errors="replace")
    
    clean_sql = _clean_sql(raw_sql)
    
    if _is_internal_query(clean_sql):
        return {"inserted": False, "timer_end": timer_end}
    
    # Extraer datos del usuario
    username = row["username"] or "unknown"
    client_ip = _extract_client_ip(row["user_host"] or "")
    
    # Timestamp
    time_str = str(row["start_time"]) if row["start_time"] else "—"
    sql_hash = _build_sql_hash(time_str, clean_sql)
    
    # Insertar
    await db.execute(
        """INSERT INTO slow_queries 
           (start_time, username, client_ip, query_time, lock_time, 
            rows_sent, rows_examined, db, sql_text, sql_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            time_str,
            username,
            client_ip,
            query_time,
            0.0,  # lock_time: performance_schema no lo provee directamente
            row["rows_sent"] or 0,
            row["rows_examined"] or 0,
            row["db"],
            clean_sql,
            sql_hash
        )
    )
    
    logger.debug(
        f"💾 Guardada: {query_time:.3f}s | "
        f"user={username} ip={client_ip} | {clean_sql[:50]}..."
    )
    
    return {"inserted": True, "timer_end": timer_end}


async def _cleanup_old_rows(db) -> None:
    """Mantiene solo las últimas MAX_CACHED consultas."""
    await db.execute(
        """DELETE FROM slow_queries WHERE id NOT IN (
            SELECT id FROM slow_queries ORDER BY id DESC LIMIT ?
        )""",
        (MAX_CACHED,)
    )


# ══════════════════════════════════════════════════════════════
# LECTURA: SQLite → API (para la web)
# ══════════════════════════════════════════════════════════════

async def get_cached_queries(
    min_time: Optional[float] = None,
    max_time: Optional[float] = None,
    db_name: Optional[str] = None,
    user: Optional[str] = None,
    date_from: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Lee consultas lentas desde SQLite con filtros opcionales.
    
    Esta función NUNCA consulta performance_schema.
    Es la que usa la API para responder a la web.
    """
    conditions = []
    params: List[Any] = []
    
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
        conditions.append("username = ?")
        params.append(user)
    if date_from:
        conditions.append("date(start_time) >= ?")
        params.append(date_from)
    
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Total de resultados
            cursor = await db.execute(
                f"SELECT COUNT(*) FROM slow_queries{where}",
                params
            )
            total = (await cursor.fetchone())[0]
            
            # Datos paginados
            cursor = await db.execute(
                f"""SELECT id, start_time, username, client_ip, query_time, lock_time,
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
                    "id": r[0],
                    "start_time": r[1],
                    "username": r[2],
                    "client_ip": r[3],
                    "query_time": r[4],
                    "lock_time": r[5],
                    "rows_sent": r[6],
                    "rows_examined": r[7],
                    "db": r[8],
                    "sql_text": r[9],
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.error(f"Error leyendo SQLite slow: {e}")
        return {"total": 0, "data": [], "error": str(e)}


async def get_slow_databases() -> List[str]:
    """Retorna bases de datos únicas del caché."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT db FROM slow_queries "
            "WHERE db IS NOT NULL AND db != '' "
            "ORDER BY db"
        )
        return [r[0] for r in await cursor.fetchall()]


async def get_slow_users() -> List[str]:
    """Retorna usuarios únicos del caché."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT username FROM slow_queries "
            "WHERE username IS NOT NULL AND username != '' AND username != 'unknown' "
            "ORDER BY username"
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


async def cache_slow_queries(min_time: float = 0.5, limit: int = 100) -> int:
    """Endpoint legacy. Redirige a sync_slow_to_sqlite."""
    return await sync_slow_to_sqlite()