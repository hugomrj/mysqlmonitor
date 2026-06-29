import json
import aiosqlite
from pathlib import Path
from config import AppSettings

DB_PATH = Path(__file__).parent / "monitor.db"


async def init_db():
    """Crea la tabla de configuración si no existe."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.commit()


async def load_config() -> AppSettings:
    """Carga la configuración desde SQLite.
    Si no existe, crea una con valores por defecto."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT value FROM config WHERE key = 'app_settings'"
        )
        row = await cursor.fetchone()

        if row is None:
            # Primera vez: guardar defaults
            default = AppSettings()
            await db.execute(
                "INSERT INTO config (key, value) VALUES (?, ?)",
                ("app_settings", default.model_dump_json())
            )
            await db.commit()
            return default

        return AppSettings.model_validate_json(row[0])


async def save_config(settings: AppSettings):
    """Guarda la configuración en SQLite.
    El background loop la leerá en el siguiente ciclo."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("app_settings", settings.model_dump_json())
        )
        await db.commit()   