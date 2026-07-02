# /routers/config.py
from fastapi import APIRouter, HTTPException
from database import load_config, save_config
from mysql_pool import create_pool
from config import AppSettings

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=AppSettings)
async def get_config():
    """Devuelve la configuración actual."""
    return await load_config()


@router.put("", response_model=AppSettings)
async def update_config(new_config: AppSettings):
    """Actualiza la configuración en caliente."""
    await save_config(new_config)
    await create_pool(new_config.mysql)
    return new_config


@router.get("/test-connection")
async def test_connection():
    """Prueba la conexión a MySQL con la config actual."""
    from mysql_pool import is_connected
    connected = await is_connected()
    return {"connected": connected}