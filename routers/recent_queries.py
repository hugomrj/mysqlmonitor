"""
Router para consultas recientes en memoria
"""
from fastapi import APIRouter, Query
from services import recent_queries

router = APIRouter(prefix="/api/queries/recent", tags=["recent-queries"])


@router.get("")
async def get_recent(
    limit: int = Query(default=100, ge=1, le=500),
    min_time_ms: float = Query(default=None, ge=0),
    database: str = Query(default=None),
    username: str = Query(default=None),
):
    """Obtiene consultas recientes con filtros."""
    queries = await recent_queries.get_recent_queries(
        limit=limit,
        min_time_ms=min_time_ms,
        database=database,
        username=username,
    )
    return {
        "total": len(queries),
        "data": queries,
    }


@router.get("/stats")
async def get_stats():
    """Estadísticas de consultas recientes."""
    return await recent_queries.get_stats()


@router.delete("")
async def clear_recent():
    """Limpia el buffer de consultas recientes."""
    await recent_queries.clear()
    return {"success": True, "message": "Buffer limpiado"}