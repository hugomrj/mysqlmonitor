from fastapi import APIRouter, Query
from database import load_config
from collectors.slow_queries import collect

router = APIRouter(prefix="/api/slow-queries", tags=["slow-queries"])


@router.get("")
async def get_slow_queries(
    min_time: float = Query(default=None, description="Tiempo mínimo en segundos"),
    limit: int = Query(default=50, ge=1, le=500),
):
    """Consultas lentas del Slow Query Log."""
    config = await load_config()
    threshold = min_time if min_time is not None else config.alerts.slow_query_time
    return await collect(min_time=threshold, limit=limit)