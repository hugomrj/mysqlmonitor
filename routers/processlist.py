from fastapi import APIRouter
from collectors.processlist import collect

router = APIRouter(prefix="/api/processlist", tags=["processlist"])


@router.get("")
async def get_processlist():
    """Sesiones activas actuales (SHOW FULL PROCESSLIST)."""
    return await collect()