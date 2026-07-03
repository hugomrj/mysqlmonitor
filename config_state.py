"""
Estado global de configuración en memoria.
"""
from __future__ import annotations
from typing import Optional
from config import AppSettings
import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "monitor.db"
_current_config: Optional[AppSettings] = None


def get_current_config() -> AppSettings:
    """Retorna la config actual en memoria. Si no hay, la carga de SQLite (síncrono)."""
    global _current_config
    if _current_config is None:
        try:
            conn = sqlite3.connect(str(DB_PATH))
            row = conn.execute(
                "SELECT value FROM config WHERE key = 'app_settings'"
            ).fetchone()
            conn.close()
            if row:
                _current_config = AppSettings.model_validate_json(row[0])
            else:
                _current_config = AppSettings()
        except Exception:
            _current_config = AppSettings()
    return _current_config


def set_current_config(config: AppSettings) -> None:
    """Actualiza la config en memoria."""
    global _current_config
    _current_config = config


def get_mysql_config_dict() -> dict:
    """Retorna la config MySQL como dict."""
    return get_current_config().mysql.model_dump()