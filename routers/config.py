from fastapi import APIRouter, HTTPException
from database import load_config, save_config
from mysql_pool import create_pool
from config import AppSettings
from services.metrics_loop import stop, start

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=AppSettings)
async def get_config():
    """Devuelve la configuración actual."""
    return await load_config()


@router.put("", response_model=AppSettings)
async def update_config(new_config: AppSettings):
    """Actualiza la configuración en caliente.
    - Se guarda en SQLite inmediatamente
    - El pool de MySQL se recrea si cambió la conexión
    - El intervalo se aplica en el siguiente ciclo del loop"""
    await save_config(new_config)

    # Reconectar MySQL si cambió la config de conexión
    await create_pool(new_config.mysql)

    return new_config


@router.get("/test-connection")
async def test_connection():
    """Prueba la conexión a MySQL con la config actual."""
    from mysql_pool import is_connected
    connected = await is_connected()
    return {"connected": connected}