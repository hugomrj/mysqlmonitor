#database.py
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


async def init_binlog_tables(db_path: str = "monitor.db"):
    """Crea tablas para auditoría de eventos del binlog."""
    async with aiosqlite.connect(db_path) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS binlog_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time TEXT NOT NULL,
                event_type TEXT NOT NULL,
                schema_name TEXT,
                table_name TEXT,
                affected_rows INTEGER DEFAULT 1,
                row_data TEXT,
                log_file TEXT,
                log_pos INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_bl_ev_time ON binlog_events(event_time);
            CREATE INDEX IF NOT EXISTS idx_bl_ev_st ON binlog_events(schema_name, table_name);
            CREATE INDEX IF NOT EXISTS idx_bl_ev_type ON binlog_events(event_type);

            CREATE TABLE IF NOT EXISTS binlog_position (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                log_file TEXT NOT NULL,
                log_pos INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        await db.commit()        




async def init_slow_queries_table(db_path: str = "monitor.db"):
    """Crea tabla para cachear consultas lentas.
    MEJORADO: Incluye columna client_ip."""
    async with aiosqlite.connect(db_path) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS slow_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                user_host TEXT,
                client_ip TEXT DEFAULT 'unknown',
                query_time REAL NOT NULL,
                lock_time TEXT,
                rows_sent INTEGER DEFAULT 0,
                rows_examined INTEGER DEFAULT 0,
                db TEXT,
                sql_text TEXT,
                sql_hash TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_sq_time ON slow_queries(start_time);
            CREATE INDEX IF NOT EXISTS idx_sq_db ON slow_queries(db);
            CREATE INDEX IF NOT EXISTS idx_sq_qt ON slow_queries(query_time);
            CREATE INDEX IF NOT EXISTS idx_sq_ip ON slow_queries(client_ip);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sq_hash ON slow_queries(sql_hash);
        """)
        await db.commit()
        
        # MIGRACIÓN: Si la tabla ya existe sin la columna client_ip, agregarla
        try:
            await db.execute("ALTER TABLE slow_queries ADD COLUMN client_ip TEXT DEFAULT 'unknown'")
            await db.commit()
            logger.info("Columna client_ip agregada a slow_queries")
        except Exception:
            pass  # La columna ya existe




async def init_queries_cache_table(db_path: str = "monitor.db"):
    """Crea tabla para cachear consultas (performance_schema)."""
    async with aiosqlite.connect(db_path) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS queries_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time TEXT NOT NULL,
                user_host TEXT,
                user_name TEXT,
                command_type TEXT,
                db TEXT,
                sql_text TEXT,
                sql_hash TEXT UNIQUE,
                query_time REAL DEFAULT 0,
                lock_time REAL DEFAULT 0,
                rows_examined INTEGER DEFAULT 0,
                rows_sent INTEGER DEFAULT 0,
                exec_count INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_qc_time ON queries_cache(event_time);
            CREATE INDEX IF NOT EXISTS idx_qc_user ON queries_cache(user_name);
            CREATE INDEX IF NOT EXISTS idx_qc_db ON queries_cache(db);
        """)
        await db.commit()     