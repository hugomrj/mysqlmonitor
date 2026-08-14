#routers/recent_queries.py
"""
Router para consultas recientes en memoria
"""
from fastapi import APIRouter, Query
from services import recent_queries

router = APIRouter(prefix="/api/queries/recent", tags=["recent-queries"])


@router.get("")
async def get_recent(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    min_time_ms: float = Query(default=None, ge=0),
    database: str = Query(default=None),
    username: str = Query(default=None),
):
    """Obtiene consultas recientes con filtros y paginación."""
    # Obtener todas las consultas filtradas
    queries = await recent_queries.get_recent_queries(
        limit=10000,  # Obtener todas para poder paginar correctamente
        min_time_ms=min_time_ms,
        database=database,
        username=username,
    )
    
    total = len(queries)
    
    # Aplicar paginación manual
    paginated = queries[offset:offset + limit]
    
    # Obtener error de permisos si existe
    perm_error = await recent_queries.get_permission_error()
    
    response = {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": paginated,
    }
    
    if perm_error:
        response["permission_error"] = perm_error
    
    return response


@router.get("/stats")
async def get_stats():
    """Estadísticas de consultas recientes."""
    return await recent_queries.get_stats()


@router.delete("")
async def clear_recent():
    """Limpia el buffer de consultas recientes."""
    await recent_queries.clear()
    return {"success": True, "message": "Buffer limpiado"}