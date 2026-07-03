"""
Estado global de configuración en memoria.
Se actualiza al guardar config y el binlog lo lee en cada reconexión.
"""
from __future__ import annotations
from typing import Optional
from config import AppSettings
import asyncio


_current_config: Optional[AppSettings] = None


def get_current_config() -> AppSettings:
    """Retorna la config actual en memoria. Si no hay, la carga de SQLite."""
    global _current_config
    if _current_config is None:
        from database import load_config
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                _current_config = pool.submit(asyncio.run, load_config()).result()
        else:
            _current_config = loop.run_until_complete(load_config())
    return _current_config


def set_current_config(config: AppSettings) -> None:
    """Actualiza la config en memoria (se llama desde el router)."""
    global _current_config
    _current_config = config


def get_mysql_config_dict() -> dict:
    """Retorna la config MySQL como dict para compatibilidad con código existente."""
    return get_current_config().mysql.dict()
