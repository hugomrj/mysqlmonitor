#routers/slow.py
"""
Router para consultas lentas (histórico persistente en SQLite).
"""
import logging
from fastapi import APIRouter, Query
from services.slow_cache import (
    get_cached_queries,
    get_slow_databases,
    get_slow_users,
    clear_cached_queries,
    cache_slow_queries,
    get_permission_error,
)

logger = logging.getLogger("mysql_monitor.routers.slow")

router = APIRouter(prefix="/api/slow-queries", tags=["slow-queries"])


@router.get("")
async def get_slow_queries(
    min_time: float = Query(default=None),
    max_time: float = Query(default=None),
    db: str = Query(default=None),
    user: str = Query(default=None),
    date_from: str = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Obtiene consultas lentas con filtros opcionales."""
    try:
        result = await get_cached_queries(
            min_time=min_time,
            max_time=max_time,
            db_name=db,
            user=user,
            date_from=date_from,
            limit=limit,
            offset=offset,
        )
        
        # Agregar error de permisos si existe
        perm_error = await get_permission_error()
        if perm_error:
            result["permission_error"] = perm_error
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error en GET /api/slow-queries: {e}", exc_info=True)
        raise


@router.get("/databases")
async def list_slow_databases():
    """Lista bases de datos únicas del caché."""
    try:
        return await get_slow_databases()
    except Exception as e:
        logger.error(f"❌ Error en GET /api/slow-queries/databases: {e}", exc_info=True)
        raise


@router.get("/users")
async def list_slow_users():
    """Lista usuarios únicos del caché."""
    try:
        return await get_slow_users()
    except Exception as e:
        logger.error(f"❌ Error en GET /api/slow-queries/users: {e}", exc_info=True)
        raise


@router.delete("")
async def delete_slow_cache():
    """Borra todo el caché de consultas lentas."""
    try:
        deleted = await clear_cached_queries()
        return {"deleted": deleted}
    except Exception as e:
        logger.error(f"❌ Error en DELETE /api/slow-queries: {e}", exc_info=True)
        raise


@router.post("/force-cache")
async def force_cache():
    """Fuerza sincronización manual (solo para debug)."""
    try:
        count = await cache_slow_queries(min_time=0.5)
        return {"cached": count}
    except Exception as e:
        logger.error(f"❌ Error en POST /api/slow-queries/force-cache: {e}", exc_info=True)
        raise