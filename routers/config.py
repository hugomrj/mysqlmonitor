# /routers/config.py
from fastapi import APIRouter
from database import load_config, save_config
from mysql_pool import create_pool
from config import AppSettings
from config_state import set_current_config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("", response_model=AppSettings)
async def get_config():
    return await load_config()


@router.put("", response_model=AppSettings)
async def update_config(new_config: AppSettings):
    await save_config(new_config)
    set_current_config(new_config)
    await create_pool(new_config.mysql)
    
    # Manejar binlog streamer
    from services.binlog_stream import binlog_service
    mysql_dict = new_config.mysql.model_dump()
    
    if new_config.binlog_enabled and new_config.mysql.password:
        if binlog_service.is_running:
            await binlog_service.restart(mysql_dict)
        else:
            await binlog_service.start(mysql_dict)
    else:
        if binlog_service.is_running:
            await binlog_service.stop()
    
    return new_config


@router.get("/test-connection")
async def test_connection():
    from mysql_pool import is_connected
    connected = await is_connected()
    return {"connected": connected}