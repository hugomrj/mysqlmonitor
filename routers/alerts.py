from fastapi import APIRouter
from services.alerts import get_active

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def get_alerts():
    """Alertas activas actuales."""
    return get_active()