# services/slow_log_config.py
"""
Servicio para configurar slow_log dinámicamente sin editar my.cnf.
Valida que el umbral sea >= 1 segundo siempre.
"""
import logging
from mysql_pool import get_pool

logger = logging.getLogger("slow_log_config")

# ═══ VALIDACIÓN GLOBAL ═══
MIN_THRESHOLD = 1.0
MAX_THRESHOLD = 60.0


def _validate_threshold(threshold: float) -> float:
    """Valida y normaliza el umbral. Siempre >= 1 y <= 60."""
    if threshold is None:
        return 3.0
    try:
        t = float(threshold)
    except (TypeError, ValueError):
        logger.warning(f"Umbral inválido '{threshold}', usando 3.0")
        return 3.0
    
    if t < MIN_THRESHOLD:
        logger.warning(f"Umbral {t}s es menor a {MIN_THRESHOLD}s, ajustando a {MIN_THRESHOLD}s")
        return MIN_THRESHOLD
    if t > MAX_THRESHOLD:
        logger.warning(f"Umbral {t}s es mayor a {MAX_THRESHOLD}s, ajustando a {MAX_THRESHOLD}s")
        return MAX_THRESHOLD
    return t


async def apply_slow_log_config(threshold: float, enabled: bool = True, log_no_indexes: bool = True):
    """
    Aplica la configuración de slow_log a MySQL.
    SE EJECUTA: al arrancar la app y cuando el usuario cambia el umbral.
    Valida que el umbral sea >= 1 segundo.
    """
    # ═══ VALIDAR UMBRAL ═══
    threshold = _validate_threshold(threshold)
    
    pool = await get_pool()
    if not pool:
        return {"success": False, "error": "No hay conexión a MySQL"}
    
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # ═══ ORDEN CRÍTICO ═══
                
                # 1. Desactivar slow_log (libera locks)
                await cur.execute("SET GLOBAL slow_query_log = OFF")
                
                # 2. Corregir archivo si es necesario (por compatibilidad)
                try:
                    await cur.execute("SELECT @@datadir")
                    row = await cur.fetchone()
                    if row:
                        datadir = row[0].rstrip('/').rstrip('\\')
                        new_file = f"{datadir}/mysql-slow.log"
                        await cur.execute(f"SET GLOBAL slow_query_log_file = '{new_file}'")
                except Exception as e:
                    logger.debug(f"No se pudo ajustar slow_query_log_file: {e}")
                
                # 3. Usar TABLE (no archivos)
                await cur.execute("SET GLOBAL log_output = 'TABLE'")
                
                # 4. ═══ SET DEL UMBRAL (el comando clave) ═══
                await cur.execute(f"SET GLOBAL long_query_time = {threshold}")
                logger.info(f"⏱️  SET GLOBAL long_query_time = {threshold}")
                
                # 5. Configurar sin índices
                await cur.execute(f"SET GLOBAL log_queries_not_using_indexes = {'ON' if log_no_indexes else 'OFF'}")
                
                # 6. Activar/desactivar
                if enabled:
                    await cur.execute("SET GLOBAL slow_query_log = ON")
                
                # 7. ═══ VERIFICAR QUE SE APLICÓ ═══
                await cur.execute("SHOW VARIABLES LIKE 'long_query_time'")
                row = await cur.fetchone()
                applied = float(row[1]) if row else threshold
                
                logger.info(f"✅ Slow log configurado: threshold={applied}s (solicitado: {threshold}s), enabled={enabled}")
                
                return {
                    "success": True,
                    "threshold": applied,
                    "enabled": enabled,
                    "log_no_indexes": log_no_indexes,
                }
    except Exception as e:
        logger.error(f"❌ Error configurando slow_log: {e}")
        return {"success": False, "error": str(e)}


async def get_current_slow_log_config():
    """Obtiene la configuración actual de slow_log desde MySQL."""
    pool = await get_pool()
    if not pool:
        return None
    
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                config = {}
                
                await cur.execute("SHOW VARIABLES LIKE 'slow_query_log'")
                row = await cur.fetchone()
                config["enabled"] = row[1] == "ON" if row else False
                
                await cur.execute("SHOW VARIABLES LIKE 'long_query_time'")
                row = await cur.fetchone()
                config["threshold"] = float(row[1]) if row else 3.0
                
                await cur.execute("SHOW VARIABLES LIKE 'log_queries_not_using_indexes'")
                row = await cur.fetchone()
                config["log_no_indexes"] = row[1] == "ON" if row else False
                
                await cur.execute("SHOW VARIABLES LIKE 'log_output'")
                row = await cur.fetchone()
                config["log_output"] = row[1] if row else "FILE"
                
                await cur.execute("SHOW VARIABLES LIKE 'slow_query_log_file'")
                row = await cur.fetchone()
                config["log_file"] = row[1] if row else "unknown"
                
                return config
    except Exception as e:
        logger.error(f"Error obteniendo configuración de slow_log: {e}")
        return None


async def ensure_performance_schema_enabled():
    """Verifica que performance_schema esté activo."""
    pool = await get_pool()
    if not pool:
        return False
    
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SHOW VARIABLES LIKE 'performance_schema'")
                row = await cur.fetchone()
                return row[1] == "ON" if row else False
    except Exception as e:
        logger.error(f"Error verificando performance_schema: {e}")
        return False