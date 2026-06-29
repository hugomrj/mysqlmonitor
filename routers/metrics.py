from fastapi import APIRouter
from services.metrics_loop import get_last_snapshot

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/snapshot")
async def get_snapshot():
    """Devuelve el último snapshot de métricas.
    Útil para que el frontend obtenga datos iniciales
    antes de conectarse al WebSocket."""
    return get_last_snapshot()