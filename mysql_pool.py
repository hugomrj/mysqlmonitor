import aiomysql
import logging
from config import MySQLConnectionConfig

logger = logging.getLogger("mysql_monitor.pool")

_pool: aiomysql.Pool | None = None
_current_dsn: str = ""


async def create_pool(config: MySQLConnectionConfig):
    """Crea o recrea el pool de conexiones a MySQL.
    Si ya existía uno con la misma configuración, no hace nada.
    Si cambió la configuración, cierra el anterior y crea uno nuevo."""
    global _pool, _current_dsn

    new_dsn = config.dsn

    # Si es la misma config, no reconectar
    if _pool is not None and _current_dsn == new_dsn:
        return _pool

    # Cerrar pool anterior si existe
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        logger.info("Pool anterior cerrado")

    try:
        _pool = await aiomysql.create_pool(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            charset=config.charset,
            autocommit=True,
            minsize=1,
            maxsize=3,
            pool_recycle=300,
            connect_timeout=5,
        )
        _current_dsn = new_dsn
        logger.info(f"Pool creado: {config.host}:{config.port}")
        return _pool

    except Exception as e:
        logger.error(f"Error conectando a MySQL: {e}")
        _pool = None
        _current_dsn = ""
        return None


async def get_pool() -> aiomysql.Pool | None:
    """Devuelve el pool actual (puede ser None si no hay conexión)."""
    return _pool


async def close_pool():
    """Cierra el pool al apagar la aplicación."""
    global _pool, _current_dsn
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        _current_dsn = ""
        logger.info("Pool cerrado")


async def is_connected() -> bool:
    """Verifica si el pool está activo haciendo un ping."""
    if _pool is None:
        return False
    try:
        async with _pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
        return True
    except Exception:
        return False